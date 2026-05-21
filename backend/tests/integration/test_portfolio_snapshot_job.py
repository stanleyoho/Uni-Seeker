"""Integration tests for `app.services.portfolio.snapshot_job` — Phase 5.

Covers the daily snapshot job that writes `holdings_snapshots`:
  J01 take_daily_snapshot_for_user creates per-account + user-wide rows
  J02 upsert overwrites the same-day row (idempotent re-run)
  J03 empty portfolio → user-wide row written with all zeros
  J04 multi-account portfolio rolls up correctly across accounts
  J05 take_daily_snapshot_for_all_active_users discovers users from
      portfolio_accounts and snapshots each one
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.db.models.portfolio import (
    HoldingsSnapshot,
    PortfolioAccount,
)
from app.models.enums import Market, UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import (
    LivePriceFetcher,
    PriceQuote,
)
from app.services.portfolio import (
    PortfolioAccountService,
    PortfolioTradeService,
)
from app.services.portfolio.snapshot_job import (
    take_daily_snapshot_for_all_active_users,
    take_daily_snapshot_for_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _MockFetcher:
    """Deterministic in-memory `LivePriceFetcher` for the snapshot job."""

    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None):
        self._quotes = quotes or {}

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid not in self._quotes:
                continue
            last, prev = self._quotes[sid]
            out[sid] = PriceQuote(
                stock_id=sid,
                last_price=last,
                prev_close=prev,
                as_of=datetime(2026, 5, 10, tzinfo=UTC),
            )
        return out


_proto_check: LivePriceFetcher = _MockFetcher()  # type: ignore[assignment]


async def _mk_user(
    db: AsyncSession,
    email: str,
    username: str,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_buy(
    db: AsyncSession,
    user: User,
    account_id: int,
    symbol: str = "2330",
    qty: str = "100",
    price: str = "500",
    trade_date: date = date(2026, 5, 1),
) -> None:
    svc = PortfolioTradeService(db, user)
    await svc.record_trade(
        account_id=account_id,
        action="BUY",
        symbol=symbol,
        market=Market.TW_TWSE,
        qty=Decimal(qty),
        price=Decimal(price),
        trade_date=trade_date,
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────
# J01 — single-user happy path
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_J01_take_daily_snapshot_for_user_creates_rows(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "j1@x.tw", "j1")
    svc = PortfolioAccountService(db_session, user)
    acc = await svc.create_account(name="J1", market=Market.TW_TWSE)
    await db_session.commit()
    await _seed_buy(db_session, user, acc.id)

    fetcher = _MockFetcher({"2330": (Decimal("550"), Decimal("540"))})
    rows_written = await take_daily_snapshot_for_user(
        db_session,
        user_id=user.id,
        live_price_fetcher=fetcher,
        snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()
    # 1 account + 1 user-wide = 2 rows.
    assert rows_written == 2

    snaps = (
        await db_session.execute(
            select(HoldingsSnapshot).where(HoldingsSnapshot.user_id == user.id)
        )
    ).scalars().all()
    assert len(snaps) == 2
    # User-wide row mirrors the single per-account total_value (550 * 100).
    user_wide = next(s for s in snaps if s.account_id is None)
    assert user_wide.total_value == Decimal("55000")
    assert user_wide.position_count == 1


# ─────────────────────────────────────────────────────────────────────
# J02 — UPSERT overwrites same-day row (idempotency)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_J02_upsert_overwrites_same_day(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "j2@x.tw", "j2")
    svc = PortfolioAccountService(db_session, user)
    acc = await svc.create_account(name="J2", market=Market.TW_TWSE)
    await db_session.commit()
    await _seed_buy(db_session, user, acc.id)

    # First snapshot: last_price = 550
    fetcher1 = _MockFetcher({"2330": (Decimal("550"), Decimal("540"))})
    await take_daily_snapshot_for_user(
        db_session, user_id=user.id, live_price_fetcher=fetcher1,
        snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()

    # Second snapshot same day with a different price → overwrite, no dup.
    fetcher2 = _MockFetcher({"2330": (Decimal("600"), Decimal("550"))})
    await take_daily_snapshot_for_user(
        db_session, user_id=user.id, live_price_fetcher=fetcher2,
        snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()

    snaps = (
        await db_session.execute(
            select(HoldingsSnapshot).where(HoldingsSnapshot.user_id == user.id)
        )
    ).scalars().all()
    # Still exactly 2 rows (per-account + user-wide), not 4.
    assert len(snaps) == 2
    user_wide = next(s for s in snaps if s.account_id is None)
    # Reflects the *second* fetcher (600 × 100).
    assert user_wide.total_value == Decimal("60000")


# ─────────────────────────────────────────────────────────────────────
# J03 — empty portfolio (no positions) → only user-wide row, zeros
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_J03_empty_portfolio_writes_user_wide_zeros(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "j3@x.tw", "j3")
    # No accounts → no per-account snapshots; only the user-wide row.
    rows_written = await take_daily_snapshot_for_user(
        db_session,
        user_id=user.id,
        live_price_fetcher=_MockFetcher(),
        snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()
    assert rows_written == 1

    snaps = (
        await db_session.execute(
            select(HoldingsSnapshot).where(HoldingsSnapshot.user_id == user.id)
        )
    ).scalars().all()
    assert len(snaps) == 1
    assert snaps[0].account_id is None
    assert snaps[0].total_value == Decimal("0")
    assert snaps[0].position_count == 0


# ─────────────────────────────────────────────────────────────────────
# J04 — multi-account roll-up
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_J04_multi_account_rollup(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "j4@x.tw", "j4")
    svc = PortfolioAccountService(db_session, user)
    acc1 = await svc.create_account(name="J4a", market=Market.TW_TWSE)
    acc2 = await svc.create_account(name="J4b", market=Market.TW_TWSE)
    await db_session.commit()
    await _seed_buy(db_session, user, acc1.id, symbol="2330", qty="100", price="500")
    await _seed_buy(db_session, user, acc2.id, symbol="2317", qty="200", price="100")

    fetcher = _MockFetcher({
        "2330": (Decimal("550"), Decimal("540")),
        "2317": (Decimal("110"), Decimal("100")),
    })
    rows_written = await take_daily_snapshot_for_user(
        db_session, user_id=user.id, live_price_fetcher=fetcher,
        snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()
    # 2 per-account + 1 user-wide = 3.
    assert rows_written == 3

    snaps = (
        await db_session.execute(
            select(HoldingsSnapshot).where(HoldingsSnapshot.user_id == user.id)
        )
    ).scalars().all()
    by_acc = {s.account_id: s for s in snaps}
    assert by_acc[acc1.id].total_value == Decimal("55000")  # 550*100
    assert by_acc[acc2.id].total_value == Decimal("22000")  # 110*200
    user_wide = by_acc[None]
    assert user_wide.total_value == Decimal("77000")
    assert user_wide.position_count == 2


# ─────────────────────────────────────────────────────────────────────
# J05 — multi-user discovery
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_J05_all_active_users_discovered(
    db_session: AsyncSession,
) -> None:
    u1 = await _mk_user(db_session, "j5a@x.tw", "j5a")
    u2 = await _mk_user(db_session, "j5b@x.tw", "j5b")
    # u3 has NO account → must be skipped.
    _u3 = await _mk_user(db_session, "j5c@x.tw", "j5c")

    s1 = PortfolioAccountService(db_session, u1)
    s2 = PortfolioAccountService(db_session, u2)
    a1 = await s1.create_account(name="u1", market=Market.TW_TWSE)
    a2 = await s2.create_account(name="u2", market=Market.TW_TWSE)
    await db_session.commit()
    await _seed_buy(db_session, u1, a1.id)
    await _seed_buy(db_session, u2, a2.id)

    fetcher = _MockFetcher({"2330": (Decimal("550"), Decimal("540"))})
    rows = await take_daily_snapshot_for_all_active_users(
        db_session, fetcher, snapshot_date=date(2026, 5, 19),
    )
    await db_session.commit()

    # Each active user has 1 account + 1 user-wide = 2 rows.
    assert sorted(rows.keys()) == sorted([u1.id, u2.id])
    assert rows[u1.id] == 2
    assert rows[u2.id] == 2

    # u3 (no portfolio) is not in the dict.
    cnt = (
        await db_session.execute(
            select(HoldingsSnapshot)
        )
    ).scalars().all()
    assert len(cnt) == 4
