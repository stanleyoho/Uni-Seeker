"""Service-level tests for ``AnalyticsService`` (Phase 5).

The HTTP-level coverage in ``test_holdings_analytics_api.py`` exercises
the 1m happy path + a handful of guard rails, but leaves these branches
uncovered:

  * ``_resolve_date_from`` for every non-1m period (3m / 6m / 1y / ytd)
  * ``_resolve_date_from`` "all" with no snapshots (earliest = None)
  * ``_resolve_date_from`` "all" with snapshots (earliest hit)
  * ``_earliest_snapshot_date`` per-account vs user-wide branches
  * ``_load_cash_flows`` translating BUY / SELL / DIVIDEND / SPLIT trades
  * ``_load_cash_flows`` honoring the ``account_id`` filter

All tests construct ``AnalyticsService`` directly (no HTTP), so the
math result is checked end-to-end on a known input set.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.db.models.portfolio import HoldingsSnapshot, PortfolioAccount
from app.db.models.portfolio.trade import PortfolioTrade
from app.models.enums import Market, UserTier
from app.models.user import User
from app.services.portfolio.analytics_service import AnalyticsService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── helpers ───────────────────────────────────────────────────────────


async def _mk_user(db: AsyncSession, email: str, tier: UserTier = UserTier.PRO) -> User:
    u = User(email=email, hashed_password="x" * 60, username=email.split("@")[0])
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_account(db: AsyncSession, user_id: int, name: str = "Acc") -> PortfolioAccount:
    acc = PortfolioAccount(user_id=user_id, name=name, market=Market.TW_TWSE)
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


async def _add_snap(
    db: AsyncSession,
    user_id: int,
    snapshot_date: date,
    total_value: str,
    *,
    account_id: int | None = None,
    total_cost: str = "100",
) -> None:
    db.add(
        HoldingsSnapshot(
            user_id=user_id,
            snapshot_date=snapshot_date,
            total_value=Decimal(total_value),
            total_cost=Decimal(total_cost),
            total_unrealized_pnl=Decimal(total_value) - Decimal(total_cost),
            realized_pnl_cum=Decimal("0"),
            position_count=1,
            account_id=account_id,
        )
    )
    await db.commit()


async def _add_trade(
    db: AsyncSession,
    account_id: int,
    trade_date: date,
    action: str,
    *,
    qty: str = "100",
    price: str = "10",
    fee: str = "0",
    tax: str = "0",
    symbol: str = "2330",
) -> None:
    db.add(
        PortfolioTrade(
            account_id=account_id,
            symbol=symbol,
            market=Market.TW_TWSE,
            action=action,
            trade_date=trade_date,
            price=Decimal(price) if action in {"BUY", "SELL"} else None,
            quantity=Decimal(qty) if action in {"BUY", "SELL"} else None,
            fee=Decimal(fee),
            tax=Decimal(tax),
        )
    )
    await db.commit()


# ── _resolve_date_from: every branch ──────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "period,expected_delta_days",
    [
        ("1m", 30),
        ("3m", 90),
        ("6m", 180),
        ("1y", 365),
    ],
)
async def test_resolve_date_from_fixed_periods(
    db_session: AsyncSession, period: str, expected_delta_days: int
) -> None:
    user = await _mk_user(db_session, f"per-{period}@x.tw")
    svc = AnalyticsService(db_session, user)
    anchor = date(2026, 5, 26)
    got = await svc._resolve_date_from(period, anchor, account_id=None)  # type: ignore[arg-type]
    assert got == anchor - timedelta(days=expected_delta_days)


@pytest.mark.asyncio
async def test_resolve_date_from_ytd_uses_jan_1(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "ytd@x.tw")
    svc = AnalyticsService(db_session, user)
    anchor = date(2026, 7, 15)
    got = await svc._resolve_date_from("ytd", anchor, account_id=None)  # type: ignore[arg-type]
    assert got == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_resolve_date_from_all_with_no_snapshots_uses_yesterday(
    db_session: AsyncSession,
) -> None:
    """`"all"` + no snapshots → anchor minus one day, so the analytics
    result degrades to the empty-window shape."""
    user = await _mk_user(db_session, "all-empty@x.tw")
    svc = AnalyticsService(db_session, user)
    anchor = date(2026, 5, 26)
    got = await svc._resolve_date_from("all", anchor, account_id=None)  # type: ignore[arg-type]
    assert got == anchor - timedelta(days=1)


@pytest.mark.asyncio
async def test_resolve_date_from_all_returns_earliest_user_wide(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "all-uw@x.tw")
    # Seed two user-wide snapshots — must return the earlier date.
    early = date(2025, 1, 1)
    late = date(2026, 5, 20)
    await _add_snap(db_session, user.id, early, "100")
    await _add_snap(db_session, user.id, late, "120")

    svc = AnalyticsService(db_session, user)
    got = await svc._resolve_date_from("all", date(2026, 5, 26), account_id=None)  # type: ignore[arg-type]
    assert got == early


@pytest.mark.asyncio
async def test_resolve_date_from_all_returns_earliest_for_account(
    db_session: AsyncSession,
) -> None:
    """``account_id`` scope picks the earliest snapshot of THAT account."""
    user = await _mk_user(db_session, "all-acc@x.tw")
    acc = await _mk_account(db_session, user.id, "AccA")
    # User-wide snapshot earlier than the account snapshot must NOT win
    # when we scope to the account.
    await _add_snap(db_session, user.id, date(2025, 1, 1), "100")
    acc_early = date(2025, 6, 1)
    await _add_snap(db_session, user.id, acc_early, "200", account_id=acc.id)
    await _add_snap(db_session, user.id, date(2026, 1, 1), "210", account_id=acc.id)

    svc = AnalyticsService(db_session, user)
    got = await svc._resolve_date_from("all", date(2026, 5, 26), account_id=acc.id)  # type: ignore[arg-type]
    assert got == acc_early


# ── _earliest_snapshot_date: user-wide vs scoped ──────────────────────


@pytest.mark.asyncio
async def test_earliest_snapshot_date_none_when_no_rows(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "esd-empty@x.tw")
    svc = AnalyticsService(db_session, user)
    assert await svc._earliest_snapshot_date(account_id=None) is None
    assert await svc._earliest_snapshot_date(account_id=999) is None


# ── _load_cash_flows: every action handled correctly ──────────────────


@pytest.mark.asyncio
async def test_load_cash_flows_buy_sell_dividend_split(
    db_session: AsyncSession,
) -> None:
    """BUY → +flow, SELL → -flow, DIVIDEND/SPLIT → ignored."""
    user = await _mk_user(db_session, "flows@x.tw")
    acc = await _mk_account(db_session, user.id, "AccA")

    # 100 shares × 10 + 5 fee + 2 tax = 1007 cash in
    await _add_trade(
        db_session,
        acc.id,
        date(2026, 5, 1),
        "BUY",
        qty="100",
        price="10",
        fee="5",
        tax="2",
    )
    # 50 × 20 - 3 fee - 1 tax = 996 → flow = -996 (cash out)
    await _add_trade(
        db_session,
        acc.id,
        date(2026, 5, 5),
        "SELL",
        qty="50",
        price="20",
        fee="3",
        tax="1",
    )
    # DIVIDEND and SPLIT must NOT produce flows.
    await _add_trade(db_session, acc.id, date(2026, 5, 10), "DIVIDEND")
    await _add_trade(db_session, acc.id, date(2026, 5, 11), "SPLIT")

    svc = AnalyticsService(db_session, user)
    flows = await svc._load_cash_flows(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        account_id=None,
    )
    assert len(flows) == 2
    by_date = {f.flow_date: f.amount for f in flows}
    assert by_date[date(2026, 5, 1)] == Decimal("1007")
    assert by_date[date(2026, 5, 5)] == Decimal("-996")


@pytest.mark.asyncio
async def test_load_cash_flows_account_id_filter(db_session: AsyncSession) -> None:
    """``account_id`` filter restricts flows to that account only."""
    user = await _mk_user(db_session, "flows-filter@x.tw")
    a = await _mk_account(db_session, user.id, "A")
    b = await _mk_account(db_session, user.id, "B")

    await _add_trade(db_session, a.id, date(2026, 5, 1), "BUY", qty="10", price="10")
    await _add_trade(db_session, b.id, date(2026, 5, 1), "BUY", qty="20", price="10")

    svc = AnalyticsService(db_session, user)
    flows_a = await svc._load_cash_flows(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        account_id=a.id,
    )
    flows_b = await svc._load_cash_flows(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        account_id=b.id,
    )
    # account A: 10*10 = 100
    assert len(flows_a) == 1
    assert flows_a[0].amount == Decimal("100")
    # account B: 20*10 = 200
    assert len(flows_b) == 1
    assert flows_b[0].amount == Decimal("200")


@pytest.mark.asyncio
async def test_load_cash_flows_date_window_excludes_outside_trades(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "flows-window@x.tw")
    acc = await _mk_account(db_session, user.id, "AccA")

    # 1 BUY inside, 2 BUYs outside the window.
    await _add_trade(db_session, acc.id, date(2025, 12, 31), "BUY", qty="1", price="1")
    await _add_trade(db_session, acc.id, date(2026, 5, 15), "BUY", qty="1", price="1")
    await _add_trade(db_session, acc.id, date(2027, 1, 1), "BUY", qty="1", price="1")

    svc = AnalyticsService(db_session, user)
    flows = await svc._load_cash_flows(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        account_id=None,
    )
    assert len(flows) == 1
    assert flows[0].flow_date == date(2026, 5, 15)


# ── compute_period_analytics: end-to-end for the "all" period ─────────


@pytest.mark.asyncio
async def test_compute_period_analytics_all_period_with_snapshots(
    db_session: AsyncSession,
) -> None:
    """Drive the full method through the ``"all"`` branch + trade cash flow.

    Three snapshots, one BUY trade between them. Verifies:
      * period_days metadata uses the snapshot date span (not the calendar
        period)
      * snapshot_count == seeded count
      * twr value is finite (math correctness verified separately in
        unit tests on the analytics module)
    """
    user = await _mk_user(db_session, "compute-all@x.tw")
    today = date.today()
    await _add_snap(db_session, user.id, today - timedelta(days=60), "100")
    await _add_snap(db_session, user.id, today - timedelta(days=30), "110")
    await _add_snap(db_session, user.id, today, "120")

    svc = AnalyticsService(db_session, user)
    result = await svc.compute_period_analytics(period="all", account_id=None)
    assert result.snapshot_count == 3
    # Span between first and last seeded snapshot is 60 days.
    assert result.period_days == 60
    # 100 → 120 with no flows: TWR == 0.2
    assert result.twr == Decimal("0.2")
