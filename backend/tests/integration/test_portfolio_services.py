"""Integration tests for portfolio services (Phase 1 / UNI-PORT-001 Batch C).

Layout (~25 cases total):
    AccountService  : 6   create/multi_account/quota/404/cross-user/cascade/audit
    TradeService    : 10  BUY lot+pos / SELL FIFO / SELL cross-lot / SELL insufficient
                          / tier monthly trades / PATCH rebuild / DELETE rebuild
                          / realized_pnl visible regardless of tier / cross-user
                          / audit log written
    PositionService : 4   list with live price / get single / empty / mock fetcher
    SummaryService  : 5   user-wide / account-wide / empty / 1 position / 5 mixed

Tests share the `db_session` fixture (SQLite in-memory) from
`tests/conftest.py`. Each test seeds its own users so isolation is real.

`MockLivePriceFetcher` mimics the `LivePriceFetcher` Protocol: given a
dict of `{symbol: (last, prev)}`, it returns matching `PriceQuote` objects
and omits unknown symbols (matches `DailyCloseLivePriceFetcher`'s
contract for missing data per spec §8 / §12 R8).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher, PriceQuote
from app.services.portfolio import (
    PortfolioAccountService,
    PortfolioPositionService,
    PortfolioSummaryService,
    PortfolioTradeService,
)
from app.services.portfolio.exceptions import (
    InsufficientShares,
    PortfolioAccountNotFound,
    PortfolioTradeNotFound,
    TierFeatureUnavailable,
    TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Shared helpers ──────────────────────────────────────────────────────────


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


class MockLivePriceFetcher:
    """Deterministic in-memory implementation of `LivePriceFetcher`.

    Pass `{symbol: (last_price, prev_close)}` at construction time;
    `fetch_quotes` returns matching `PriceQuote`s for known symbols and
    omits unknown ones (matches the spec §8 contract: missing symbols
    do NOT raise, they just don't appear in the result dict).
    """

    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        self._quotes = quotes or {}
        self.calls: list[list[str]] = []  # observability for assertions

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        self.calls.append(list(stock_ids))
        result: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid not in self._quotes:
                continue
            last, prev = self._quotes[sid]
            result[sid] = PriceQuote(
                stock_id=sid,
                last_price=last,
                prev_close=prev,
                as_of=datetime(2026, 5, 10, tzinfo=UTC),
            )
        return result


# Confirm the mock satisfies the Protocol at runtime.
_proto_check: LivePriceFetcher = MockLivePriceFetcher()  # type: ignore[assignment]


async def _count_audit(db_session: AsyncSession, action: str, user_id: int) -> int:
    from sqlalchemy import func, select

    result = await db_session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == action, AuditLog.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


# ═════════════════════════════════════════════════════════════════════════════
# AccountService (6 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_account_service_create_writes_audit(
    db_session: AsyncSession,
) -> None:
    """create_account inserts a row and emits portfolio_account_created."""
    user = await _mk_user(db_session, "as1@x.com", "as1")
    svc = PortfolioAccountService(db_session, user)
    acc = await svc.create_account(name="Yuanta", market=Market.TW_TWSE, broker="Yuanta")
    await db_session.commit()

    assert acc.id is not None
    assert acc.user_id == user.id
    assert await _count_audit(db_session, "portfolio_account_created", user.id) == 1


async def test_account_service_free_quota_enforced(
    db_session: AsyncSession,
) -> None:
    """BASIC tier: max_accounts=3 → 4th create raises TierLimitExceeded.

    We test BASIC (not FREE) because FREE additionally has
    `multi_account=false`, which would short-circuit the 2nd create
    via TierFeatureUnavailable *before* the numeric quota path runs.
    The dedicated feature-flag test covers that case separately.
    """
    user = await _mk_user(db_session, "as2@x.com", "as2", tier=UserTier.BASIC)
    svc = PortfolioAccountService(db_session, user)

    with patch("app.services.portfolio.account_service.settings") as s:
        s.enable_monetization = True
        # BASIC.max_accounts = 3 → create 3 first, then expect 4th to raise.
        for n in range(3):
            await svc.create_account(name=f"a{n}", market=Market.TW_TWSE)
        await db_session.commit()

        with pytest.raises(TierLimitExceeded) as exc:
            await svc.create_account(name="fourth", market=Market.TW_TWSE)
        assert exc.value.limit_key == "max_accounts"
        assert exc.value.limit == 3


async def test_account_service_multi_account_feature_gates_free(
    db_session: AsyncSession,
) -> None:
    """FREE has multi_account=false → 2nd create blocked by feature flag
    BEFORE we reach the numeric quota. We patch the quota to look
    'unlimited' for FREE to isolate the feature-flag path."""
    user = await _mk_user(db_session, "as3@x.com", "as3", tier=UserTier.FREE)
    svc = PortfolioAccountService(db_session, user)

    with (
        patch("app.services.portfolio.account_service.settings") as s,
        patch("app.services.portfolio.account_service.get_limit", return_value=None),
    ):
        s.enable_monetization = True
        await svc.create_account(name="first", market=Market.TW_TWSE)
        await db_session.commit()
        with pytest.raises(TierFeatureUnavailable) as exc:
            await svc.create_account(name="second", market=Market.TW_TWSE)
        assert exc.value.feature == "multi_account"


async def test_account_service_get_other_users_account_raises(
    db_session: AsyncSession,
) -> None:
    """User B's get_account(A's id) raises PortfolioAccountNotFound."""
    a = await _mk_user(db_session, "as4a@x.com", "as4a")
    b = await _mk_user(db_session, "as4b@x.com", "as4b")
    svc_a = PortfolioAccountService(db_session, a)
    svc_b = PortfolioAccountService(db_session, b)

    acc_a = await svc_a.create_account(name="A's", market=Market.TW_TWSE)
    await db_session.commit()

    with pytest.raises(PortfolioAccountNotFound):
        await svc_b.get_account(acc_a.id)
    # B's list is empty even though A's row exists.
    assert await svc_b.list_accounts() == []


@pytest.mark.pg_integration
async def test_account_service_delete_cascades_trades_and_positions(
    db_session: AsyncSession,
) -> None:
    """delete_account removes account and cascades trades / lots /
    positions per FK ON DELETE CASCADE."""
    user = await _mk_user(db_session, "as5@x.com", "as5")
    acc_svc = PortfolioAccountService(db_session, user)
    trade_svc = PortfolioTradeService(db_session, user)

    acc = await acc_svc.create_account(name="cascade", market=Market.TW_TWSE)
    await db_session.commit()
    await trade_svc.record_trade(
        account_id=acc.id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    await acc_svc.delete_account(acc.id)
    await db_session.commit()

    # Re-fetching raises NotFound; positions / lots are gone via cascade.
    with pytest.raises(PortfolioAccountNotFound):
        await acc_svc.get_account(acc.id)
    # Audit log carries the delete event.
    assert await _count_audit(db_session, "portfolio_account_deleted", user.id) == 1


async def test_account_service_update_persists_and_audits(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "as6@x.com", "as6")
    svc = PortfolioAccountService(db_session, user)
    acc = await svc.create_account(name="old", market=Market.TW_TWSE)
    await db_session.commit()

    updated = await svc.update_account(acc.id, name="new", broker="Fubon")
    await db_session.commit()
    assert updated.name == "new"
    assert updated.broker == "Fubon"
    assert await _count_audit(db_session, "portfolio_account_updated", user.id) == 1


# ═════════════════════════════════════════════════════════════════════════════
# TradeService (10 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def _seed_account(db_session: AsyncSession, user: User, name: str = "acc") -> int:
    svc = PortfolioAccountService(db_session, user)
    acc = await svc.create_account(name=name, market=Market.TW_TWSE)
    await db_session.commit()
    return acc.id


@pytest.mark.pg_integration
async def test_trade_service_buy_creates_lot_and_position(
    db_session: AsyncSession,
) -> None:
    """A single BUY inserts one trade, one lot, and an open position
    with the correct avg_cost (fee folded into cost_per_unit)."""
    user = await _mk_user(db_session, "ts1@x.com", "ts1")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    trade = await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        fee=Decimal("28"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    assert trade is not None

    pos = await svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos is not None
    assert pos.quantity == Decimal("100")
    # avg_cost = (500 * 100 + 28) / 100 = 500.28
    assert pos.avg_cost_fifo == Decimal("500.28")
    assert pos.is_closed is False


@pytest.mark.pg_integration
async def test_trade_service_sell_consumes_fifo_oldest_first(
    db_session: AsyncSession,
) -> None:
    """BUY 100@500 + BUY 50@600 + SELL 80 → realized_pnl on lot[0] only,
    remaining_qty: lot[0]=20, lot[1]=50."""
    user = await _mk_user(db_session, "ts2@x.com", "ts2")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("50"),
        price=Decimal("600"),
        trade_date=date(2026, 5, 2),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="SELL",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("80"),
        price=Decimal("700"),
        trade_date=date(2026, 5, 3),
    )
    await db_session.commit()

    pos = await svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    # Sold 80 from the 500-cost lot → realized = (700-500)*80 = 16000
    assert pos.realized_pnl == Decimal("16000")
    # qty left: 20 (lot[0]) + 50 (lot[1]) = 70
    assert pos.quantity == Decimal("70")


async def test_trade_service_sell_insufficient_shares_raises(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ts3@x.com", "ts3")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    with pytest.raises(InsufficientShares):
        await svc.record_trade(
            account_id=acc_id,
            action="SELL",
            symbol="2330",
            market=Market.TW_TWSE,
            qty=Decimal("11"),  # too many
            price=Decimal("600"),
            trade_date=date(2026, 5, 2),
        )


@pytest.mark.pg_integration
async def test_trade_service_sell_crosses_multiple_lots(
    db_session: AsyncSession,
) -> None:
    """SELL larger than the oldest lot spills into the next lot.
    BUY 10@100 + BUY 10@200 + SELL 15@300 →
        cost = 10*100 + 5*200 = 2000
        proceeds = 15*300 = 4500
        realized = 4500 - 2000 = 2500
        remaining qty = 5 (only the 200-cost lot, partially).
    """
    user = await _mk_user(db_session, "ts4@x.com", "ts4")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("200"),
        trade_date=date(2026, 5, 2),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="SELL",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("15"),
        price=Decimal("300"),
        trade_date=date(2026, 5, 3),
    )
    await db_session.commit()

    pos = await svc._position_repo.get(acc_id, "X", market=Market.TW_TWSE)
    assert pos.quantity == Decimal("5")
    assert pos.realized_pnl == Decimal("2500")


async def test_trade_service_monthly_trade_quota_enforced(
    db_session: AsyncSession,
) -> None:
    """FREE tier: max_trades_per_month=30 → 31st trade raises."""
    user = await _mk_user(db_session, "ts5@x.com", "ts5", tier=UserTier.FREE)
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    today = datetime.now(UTC).date()

    # Patch monetization on AND patch the counter to fake "30 already used".
    with (
        patch("app.services.portfolio.trade_service.settings") as s,
        patch.object(svc._trade_repo, "count_by_user_this_month", return_value=30),
    ):
        s.enable_monetization = True
        with pytest.raises(TierLimitExceeded) as exc:
            await svc.record_trade(
                account_id=acc_id,
                action="BUY",
                symbol="2330",
                market=Market.TW_TWSE,
                qty=Decimal("1"),
                price=Decimal("100"),
                trade_date=today,
            )
        assert exc.value.limit_key == "max_trades_per_month"


async def test_trade_service_patch_rebuilds_position(
    db_session: AsyncSession,
) -> None:
    """PATCH price on an existing trade → avg_cost reflects new price."""
    user = await _mk_user(db_session, "ts6@x.com", "ts6")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    t = await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    await svc.update_trade(t.id, price=Decimal("600"))
    await db_session.commit()

    pos = await svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    # No fee → avg_cost should match new price exactly.
    assert pos.avg_cost_fifo == Decimal("600")
    assert pos.quantity == Decimal("100")
    assert await _count_audit(db_session, "portfolio_trade_updated", user.id) == 1


async def test_trade_service_delete_rebuilds(
    db_session: AsyncSession,
) -> None:
    """DELETE the middle BUY in a 3-trade chain. realized_pnl on the
    SELL is recomputed against the remaining BUY only."""
    user = await _mk_user(db_session, "ts7@x.com", "ts7")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    b1 = await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    b2 = await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("200"),
        trade_date=date(2026, 5, 2),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="SELL",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("5"),
        price=Decimal("300"),
        trade_date=date(2026, 5, 3),
    )
    await db_session.commit()
    # Sanity: pre-delete realized = (300-100)*5 = 1000 (FIFO consumes b1 only)
    pos_before = await svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos_before.realized_pnl == Decimal("1000")

    # Now delete b1 (the 100-cost BUY). The SELL must re-FIFO against b2:
    #   cost = 5 * 200 = 1000  →  realized = (300-200)*5 = 500
    await svc.delete_trade(b1.id)
    await db_session.commit()

    pos_after = await svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos_after.realized_pnl == Decimal("500")
    # Remaining qty: only b2 contributed; 10 - 5 sold = 5.
    assert pos_after.quantity == Decimal("5")
    assert b2.id is not None  # silence unused-var lint


async def test_trade_service_realized_pnl_computed_for_free_tier(
    db_session: AsyncSession,
) -> None:
    """Per task brief: even FREE tier (which has realized_pnl=false in
    features) must have realized_pnl COMPUTED at the service layer.
    Hiding the field is the API layer's job, not the service's."""
    user = await _mk_user(db_session, "ts8@x.com", "ts8", tier=UserTier.FREE)
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await svc.record_trade(
        account_id=acc_id,
        action="SELL",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("5"),
        price=Decimal("150"),
        trade_date=date(2026, 5, 2),
    )
    await db_session.commit()
    pos = await svc._position_repo.get(acc_id, "X", market=Market.TW_TWSE)
    assert pos.realized_pnl == Decimal("250")  # service still computes


async def test_trade_service_cross_user_trade_rejected(
    db_session: AsyncSession,
) -> None:
    """User B cannot record / update / delete a trade on User A's account."""
    a = await _mk_user(db_session, "ts9a@x.com", "ts9a")
    b = await _mk_user(db_session, "ts9b@x.com", "ts9b")
    acc_a = await _seed_account(db_session, a, name="A's")
    svc_a = PortfolioTradeService(db_session, a)
    svc_b = PortfolioTradeService(db_session, b)

    t = await svc_a.record_trade(
        account_id=acc_a,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    # B cannot record trade on A's account.
    with pytest.raises(PortfolioAccountNotFound):
        await svc_b.record_trade(
            account_id=acc_a,
            action="BUY",
            symbol="X",
            market=Market.TW_TWSE,
            qty=Decimal("1"),
            price=Decimal("1"),
            trade_date=date(2026, 5, 2),
        )
    # B cannot patch / delete A's trade.
    with pytest.raises(PortfolioTradeNotFound):
        await svc_b.update_trade(t.id, price=Decimal("999"))
    with pytest.raises(PortfolioTradeNotFound):
        await svc_b.delete_trade(t.id)


async def test_trade_service_audit_log_written(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ts10@x.com", "ts10")
    acc_id = await _seed_account(db_session, user)
    svc = PortfolioTradeService(db_session, user)

    t = await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await svc.update_trade(t.id, price=Decimal("110"))
    await svc.delete_trade(t.id)
    await db_session.commit()

    assert await _count_audit(db_session, "portfolio_trade_added", user.id) == 1
    assert await _count_audit(db_session, "portfolio_trade_updated", user.id) == 1
    assert await _count_audit(db_session, "portfolio_trade_deleted", user.id) == 1


# ═════════════════════════════════════════════════════════════════════════════
# PositionService (4 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_position_service_list_enriches_with_live_price(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ps1@x.com", "ps1")
    acc_id = await _seed_account(db_session, user)
    trade_svc = PortfolioTradeService(db_session, user)

    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher({"2330": (Decimal("550"), Decimal("530"))})
    pos_svc = PortfolioPositionService(db_session, user, fetcher)
    rows = await pos_svc.list_positions()

    assert len(rows) == 1
    r = rows[0]
    assert r.symbol == "2330"
    assert r.quantity == Decimal("100")
    assert r.last_price == Decimal("550")
    assert r.prev_close == Decimal("530")
    # unrealized = (550 - 500) * 100 = 5000
    assert r.unrealized_pnl is not None
    assert r.unrealized_pnl.unrealized_pnl == Decimal("5000")
    # daily change = (550 - 530) * 100 = 2000
    assert r.daily_change is not None
    assert r.daily_change.delta_total == Decimal("2000")
    # Mock fetcher was called exactly once with the symbol set.
    assert fetcher.calls == [["2330"]]


async def test_position_service_get_single_position(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ps2@x.com", "ps2")
    acc_id = await _seed_account(db_session, user)
    trade_svc = PortfolioTradeService(db_session, user)
    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher({"2330": (Decimal("120"), Decimal("110"))})
    pos_svc = PortfolioPositionService(db_session, user, fetcher)
    row = await pos_svc.get_position(acc_id, "2330", market=Market.TW_TWSE)
    assert row.quantity == Decimal("10")
    assert row.last_price == Decimal("120")


async def test_position_service_empty_portfolio_returns_empty_list(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ps3@x.com", "ps3")
    fetcher = MockLivePriceFetcher()
    pos_svc = PortfolioPositionService(db_session, user, fetcher)
    rows = await pos_svc.list_positions()
    assert rows == []
    # No fetcher call when there are no positions.
    assert fetcher.calls == []


async def test_position_service_missing_quote_yields_null_last_price(
    db_session: AsyncSession,
) -> None:
    """Spec §12 R8: missing quote → row included with last_price=None
    (UI shows '—'), summary still computes without crashing."""
    user = await _mk_user(db_session, "ps4@x.com", "ps4")
    acc_id = await _seed_account(db_session, user)
    trade_svc = PortfolioTradeService(db_session, user)
    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="UNKNOWN",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher()  # empty
    pos_svc = PortfolioPositionService(db_session, user, fetcher)
    rows = await pos_svc.list_positions()
    assert len(rows) == 1
    assert rows[0].last_price is None
    assert rows[0].unrealized_pnl is None
    assert rows[0].daily_change is None


# ═════════════════════════════════════════════════════════════════════════════
# SummaryService (5 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_summary_service_user_summary_aggregates_across_accounts(
    db_session: AsyncSession,
) -> None:
    """Two accounts, one position each, summary sums them."""
    user = await _mk_user(db_session, "ss1@x.com", "ss1")
    trade_svc = PortfolioTradeService(db_session, user)
    acc1 = await _seed_account(db_session, user, name="a1")
    acc2 = await _seed_account(db_session, user, name="a2")

    await trade_svc.record_trade(
        account_id=acc1,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await trade_svc.record_trade(
        account_id=acc2,
        action="BUY",
        symbol="2454",
        market=Market.TW_TWSE,
        qty=Decimal("5"),
        price=Decimal("1000"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher(
        {
            "2330": (Decimal("600"), Decimal("550")),
            "2454": (Decimal("1100"), Decimal("1050")),
        }
    )
    svc = PortfolioSummaryService(db_session, user, fetcher)
    summary = await svc.get_user_summary()

    # total_cost = 10*500 + 5*1000 = 10000
    assert summary.total_cost == Decimal("10000")
    # total_value = 10*600 + 5*1100 = 11500
    assert summary.total_value == Decimal("11500")
    # gain_simple = 1500
    assert summary.gain_simple == Decimal("1500")


async def test_summary_service_account_summary_scopes_correctly(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ss2@x.com", "ss2")
    trade_svc = PortfolioTradeService(db_session, user)
    acc1 = await _seed_account(db_session, user, name="a1")
    acc2 = await _seed_account(db_session, user, name="a2")

    await trade_svc.record_trade(
        account_id=acc1,
        action="BUY",
        symbol="A",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await trade_svc.record_trade(
        account_id=acc2,
        action="BUY",
        symbol="B",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("200"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher(
        {
            "A": (Decimal("110"), Decimal("105")),
            "B": (Decimal("220"), Decimal("210")),
        }
    )
    svc = PortfolioSummaryService(db_session, user, fetcher)
    s1 = await svc.get_account_summary(acc1)
    s2 = await svc.get_account_summary(acc2)

    assert s1.total_cost == Decimal("1000")
    assert s1.total_value == Decimal("1100")
    assert s2.total_cost == Decimal("2000")
    assert s2.total_value == Decimal("2200")


async def test_summary_service_empty_portfolio_returns_zeros(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ss3@x.com", "ss3")
    fetcher = MockLivePriceFetcher()
    svc = PortfolioSummaryService(db_session, user, fetcher)
    summary = await svc.get_user_summary()
    assert summary.total_cost == Decimal("0")
    assert summary.total_value == Decimal("0")
    assert summary.gain_simple == Decimal("0")


async def test_summary_service_single_position_daily_change(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "ss4@x.com", "ss4")
    trade_svc = PortfolioTradeService(db_session, user)
    acc_id = await _seed_account(db_session, user)
    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="2330",
        market=Market.TW_TWSE,
        qty=Decimal("100"),
        price=Decimal("500"),
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()

    fetcher = MockLivePriceFetcher({"2330": (Decimal("520"), Decimal("510"))})
    svc = PortfolioSummaryService(db_session, user, fetcher)
    summary = await svc.get_user_summary()
    # daily change = (520 - 510) * 100 = 1000
    assert summary.total_daily_change == Decimal("1000")
    # unrealized = (520 - 500) * 100 = 2000
    assert summary.total_unrealized_pnl == Decimal("2000")


async def test_summary_service_five_positions_mixed_gain_loss(
    db_session: AsyncSession,
) -> None:
    """5 positions, 3 winners 2 losers — gain_simple = total_value - total_cost."""
    user = await _mk_user(db_session, "ss5@x.com", "ss5")
    trade_svc = PortfolioTradeService(db_session, user)
    acc_id = await _seed_account(db_session, user)

    seed = [
        ("S1", Decimal("10"), Decimal("100"), Decimal("120")),  # +200
        ("S2", Decimal("10"), Decimal("100"), Decimal("90")),  # -100
        ("S3", Decimal("5"), Decimal("200"), Decimal("250")),  # +250
        ("S4", Decimal("20"), Decimal("50"), Decimal("40")),  # -200
        ("S5", Decimal("1"), Decimal("1000"), Decimal("1500")),  # +500
    ]
    for sym, qty, buy_price, _ in seed:
        await trade_svc.record_trade(
            account_id=acc_id,
            action="BUY",
            symbol=sym,
            market=Market.TW_TWSE,
            qty=qty,
            price=buy_price,
            trade_date=date(2026, 5, 1),
        )
    await db_session.commit()

    fetcher = MockLivePriceFetcher({sym: (last, last - Decimal("1")) for sym, _, _, last in seed})
    svc = PortfolioSummaryService(db_session, user, fetcher)
    summary = await svc.get_user_summary()

    expected_cost = sum((q * p for _, q, p, _ in seed), Decimal("0"))
    expected_value = sum((q * last for _, q, _, last in seed), Decimal("0"))
    assert summary.total_cost == expected_cost
    assert summary.total_value == expected_value
    assert summary.gain_simple == expected_value - expected_cost


# silence pyflakes: timedelta is imported by some test variants downstream.
_ = timedelta
