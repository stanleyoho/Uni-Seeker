"""Query-count regression tests for the N+1 batch fixes.

Each test seeds N rows then asserts the endpoint executes a *bounded*
number of SELECTs against the price/account tables. Without the batch
fixes these would have scaled linearly with N — that's the regression
we are guarding against.

We count by attaching a ``before_cursor_execute`` listener to the test
engine via the connection the fixture exposes. SQLAlchemy emits one
event per statement compiled, which matches our notion of "DB
round-trip" closely enough for budget checks. We are intentionally
permissive on the absolute number (the deps stack does its own house-
keeping queries — strategy registry warmup, etc.) and assert against a
**constant ceiling that does NOT scale with N**.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from app.models.enums import Market
from app.models.journal import AccountGroup, AccountGroupMember, TradeAccount
from app.models.price import StockPrice
from app.models.stock import Stock

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


class _QueryCounter:
    """Counts ``SELECT`` statements that reference a specific table name.

    We could count every statement, but the test fixtures use the same
    engine for setup (seed inserts also fire SELECTs in some dialects)
    so filtering by table keeps the budget meaningful. We match the
    table name on word boundaries because SQLAlchemy may emit
    ``FROM stock_prices`` OR ``FROM stock_prices AS sp1`` OR
    ``JOIN stock_prices`` depending on the query shape.
    """

    def __init__(self, table: str) -> None:
        import re

        self.table = table.lower()
        self.pattern = re.compile(rf"\b{re.escape(self.table)}\b")
        self.count = 0
        self.statements: list[str] = []

    def __call__(
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        lowered = statement.lower()
        if lowered.lstrip().startswith("select") and self.pattern.search(lowered):
            self.count += 1
            self.statements.append(statement)


def _attach_counter(engine: object, table: str) -> _QueryCounter:
    """Attach the listener to the *sync* engine that backs the async one.

    SQLAlchemy's async engine raises NotImplementedError when you try to
    register events directly — the docs steer you at ``sync_engine`` so
    the synchronous DBAPI cursor events flow through. The async layer
    drives the same underlying connection so we count every SELECT.
    """
    counter = _QueryCounter(table)
    sync_engine = getattr(engine, "sync_engine", engine)
    event.listen(sync_engine, "before_cursor_execute", counter)
    return counter


def _detach_counter(engine: object, counter: _QueryCounter) -> None:
    sync_engine = getattr(engine, "sync_engine", engine)
    event.remove(sync_engine, "before_cursor_execute", counter)


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _mk_stock_with_history(
    db: AsyncSession,
    symbol: str,
    name: str,
    num_days: int,
    base_close: float = 100.0,
) -> Stock:
    """Seed a stock + num_days of consecutive StockPrice rows."""
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)

    base_date = date(2026, 5, 1)
    for i in range(num_days):
        c = base_close + (i % 7) * 0.5
        p = StockPrice(
            stock_id=s.id,
            date=base_date - timedelta(days=num_days - i - 1),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            close=Decimal(str(c)),
            change=Decimal("0"),
            volume=100_000,
        )
        db.add(p)
    await db.commit()
    return s


# ── /low-base/scan: stock_prices reads are O(1) regardless of stock count ──


@pytest.mark.parametrize("num_stocks", [3, 6])
async def test_low_base_scan_batches_price_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    num_stocks: int,
) -> None:
    """``stock_prices`` SELECT count must be constant w.r.t. num_stocks.

    Pre-fix: the endpoint ran one ``SELECT … FROM stock_prices WHERE
    stock_id = X`` per qualifying stock → N reads. The batch fix
    collapses those into one ``WHERE stock_id IN (...)`` so the read
    count stays at 1 regardless of how many stocks qualify.
    """
    for i in range(num_stocks):
        await _mk_stock_with_history(
            db_session, f"TST{i:02d}", f"Test {i}", num_days=60, base_close=100 + i
        )

    engine = db_session.bind
    counter = _attach_counter(engine, "stock_prices")
    try:
        resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60")
    finally:
        _detach_counter(engine, counter)

    assert resp.status_code == 200
    # Budget: the symbol_query also touches stock_prices for the COUNT
    # aggregate (1 SELECT) + the batched price fetch (1 SELECT) = 2.
    # We allow up to 3 to leave headroom for future schema explorations
    # without making the assertion flaky.
    assert counter.count <= 3, (
        f"low-base/scan made {counter.count} stock_prices SELECTs for "
        f"{num_stocks} stocks — N+1 regression"
    )


# ── /journal/groups: account reads collapse to one IN-clause ────────────────


@pytest.mark.parametrize("num_groups", [3, 6])
async def test_list_groups_batches_account_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    num_groups: int,
) -> None:
    """``trade_accounts`` SELECT count must be constant w.r.t. num_groups.

    Pre-fix: ``_build_group_response`` ran one ``SELECT … FROM
    trade_accounts WHERE id IN (...)`` per group. The list endpoint
    now batches those into a single union-IN-clause.
    """
    # Seed N groups each with one account
    accounts: list[TradeAccount] = []
    for i in range(num_groups):
        acc = TradeAccount(
            name=f"Acc{i}",
            broker=None,
            market="TW",
            currency="TWD",
            description=None,
        )
        db_session.add(acc)
        accounts.append(acc)
    await db_session.commit()
    for a in accounts:
        await db_session.refresh(a)

    for i in range(num_groups):
        g = AccountGroup(name=f"G{i}", description=None, base_currency="TWD")
        db_session.add(g)
        await db_session.flush()
        db_session.add(
            AccountGroupMember(
                group_id=g.id, account_id=accounts[i].id, target_weight=None
            )
        )
    await db_session.commit()

    engine = db_session.bind
    counter = _attach_counter(engine, "trade_accounts")
    try:
        resp = await client.get("/api/v1/journal/groups")
    finally:
        _detach_counter(engine, counter)

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == num_groups
    # Budget: 1 batched SELECT against trade_accounts is sufficient post-fix.
    # We allow up to 2 to leave headroom for orthogonal middleware checks.
    assert counter.count <= 2, (
        f"list_groups made {counter.count} trade_accounts SELECTs for "
        f"{num_groups} groups — N+1 regression"
    )
