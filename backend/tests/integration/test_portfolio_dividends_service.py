"""Integration tests for PortfolioDividendRepo + PortfolioDividendService
(Phase 2 Batch B).

Layout (16 cases total):
    Repo    : 5  create / cross-user get / list order / update allowlist /
                 cross-user delete
    Service : 11 cash happy / stock happy / lot total cost invariant /
                 FREE blocked / BASIC ok / PRO ok / unknown account /
                 cross-user / audit log / immutable PATCH / simple delete

Tests share `db_session` (in-memory SQLite) from `tests/conftest.py`
and seed users / accounts / lots locally — no fixture coupling beyond
the session. The MockLivePriceFetcher pattern from
`test_portfolio_services.py` is NOT needed here because dividend logic
does not touch live prices.

Tier-flag behaviour is exercised via `patch(...settings)` on the
dividend_service module so we can toggle `enable_monetization=True`
selectively (rest of the suite runs with the default `False`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.user import User
from app.repositories.portfolio import (
    PortfolioDividendRepo,
)
from app.services.portfolio import (
    PortfolioAccountService,
    PortfolioDividendService,
    PortfolioTradeService,
)
from app.services.portfolio.dividend_service import (
    PortfolioDividendNotFoundError,
)
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
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


async def _seed_account(db: AsyncSession, user: User, name: str = "acc") -> int:
    svc = PortfolioAccountService(db, user)
    acc = await svc.create_account(name=name, market=Market.TW_TWSE)
    await db.commit()
    return acc.id


async def _count_audit(db: AsyncSession, action: str, user_id: int) -> int:
    result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == action, AuditLog.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


# ═════════════════════════════════════════════════════════════════════════════
# Repo cases (5)
# ═════════════════════════════════════════════════════════════════════════════


async def test_create_dividend(db_session: AsyncSession) -> None:
    """Happy path: repo.create returns a row tied to the owning account."""
    user = await _mk_user(db_session, "d1@x.com", "d1")
    acc_id = await _seed_account(db_session, user)
    repo = PortfolioDividendRepo(db_session)

    row = await repo.create(
        account_id=acc_id,
        user_id=user.id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 5),
        amount_per_share=Decimal("10"),
        quantity_at_record=Decimal("100"),
    )
    await db_session.commit()
    assert row is not None
    assert row.id is not None
    assert row.account_id == acc_id
    assert row.dividend_type == "CASH"
    assert row.amount_per_share == Decimal("10")


async def test_get_by_id_cross_user_returns_none(
    db_session: AsyncSession,
) -> None:
    """User B cannot fetch User A's dividend via repo.get_by_id."""
    a = await _mk_user(db_session, "d2a@x.com", "d2a")
    b = await _mk_user(db_session, "d2b@x.com", "d2b")
    acc_a = await _seed_account(db_session, a)
    repo = PortfolioDividendRepo(db_session)

    row_a = await repo.create(
        account_id=acc_a,
        user_id=a.id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 5),
        amount_per_share=Decimal("1"),
        quantity_at_record=Decimal("1"),
    )
    await db_session.commit()
    assert row_a is not None

    # B trying to fetch A's row → None.
    miss = await repo.get_by_id(row_a.id, user_id=b.id)
    assert miss is None
    # A still can.
    hit = await repo.get_by_id(row_a.id, user_id=a.id)
    assert hit is not None


async def test_list_by_account_orders_by_ex_date_desc(
    db_session: AsyncSession,
) -> None:
    """list_by_account returns latest ex_dividend_date first."""
    user = await _mk_user(db_session, "d3@x.com", "d3")
    acc_id = await _seed_account(db_session, user)
    repo = PortfolioDividendRepo(db_session)

    for d in [date(2026, 5, 1), date(2026, 5, 3), date(2026, 5, 2)]:
        await repo.create(
            account_id=acc_id,
            user_id=user.id,
            symbol="2330",
            market=Market.TW_TWSE,
            dividend_type="CASH",
            ex_dividend_date=d,
            amount_per_share=Decimal("1"),
            quantity_at_record=Decimal("1"),
        )
    await db_session.commit()
    rows = await repo.list_by_account(account_id=acc_id, user_id=user.id)
    assert [r.ex_dividend_date for r in rows] == [
        date(2026, 5, 3),
        date(2026, 5, 2),
        date(2026, 5, 1),
    ]


async def test_update_dividend_drops_unknown_keys(
    db_session: AsyncSession,
) -> None:
    """repo.update silently drops keys not in the mapped-column allowlist
    (immutable / unknown). Same pattern as trade_repo.update."""
    user = await _mk_user(db_session, "d4@x.com", "d4")
    acc_id = await _seed_account(db_session, user)
    repo = PortfolioDividendRepo(db_session)

    row = await repo.create(
        account_id=acc_id,
        user_id=user.id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 5),
        amount_per_share=Decimal("10"),
        quantity_at_record=Decimal("100"),
    )
    await db_session.commit()
    assert row is not None

    updated = await repo.update(
        row.id,
        user_id=user.id,
        note="bumped",
        bogus_field=999,  # unknown — silently dropped
        id=42,  # immutable — silently dropped
        account_id=99999,  # immutable — silently dropped
    )
    await db_session.commit()
    assert updated is not None
    assert updated.note == "bumped"
    assert updated.id == row.id
    assert updated.account_id == acc_id


async def test_delete_dividend_cross_user_returns_false(
    db_session: AsyncSession,
) -> None:
    """User B's repo.delete on User A's dividend is rejected."""
    a = await _mk_user(db_session, "d5a@x.com", "d5a")
    b = await _mk_user(db_session, "d5b@x.com", "d5b")
    acc_a = await _seed_account(db_session, a)
    repo = PortfolioDividendRepo(db_session)

    row_a = await repo.create(
        account_id=acc_a,
        user_id=a.id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 5),
        amount_per_share=Decimal("1"),
        quantity_at_record=Decimal("1"),
    )
    await db_session.commit()
    assert row_a is not None

    # B's delete blocked.
    assert await repo.delete(row_a.id, user_id=b.id) is False
    # Row still exists.
    assert await repo.get_by_id(row_a.id, user_id=a.id) is not None
    # A can still delete.
    assert await repo.delete(row_a.id, user_id=a.id) is True
    await db_session.commit()


# ═════════════════════════════════════════════════════════════════════════════
# Service cases (11)
# ═════════════════════════════════════════════════════════════════════════════


async def _seed_position(
    db_session: AsyncSession,
    user: User,
    acc_id: int,
    symbol: str = "2330",
    qty: Decimal = Decimal("100"),
    price: Decimal = Decimal("500"),
) -> None:
    """Use the trade service to create a real position (BUY)."""
    svc = PortfolioTradeService(db_session, user)
    await svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol=symbol,
        market=Market.TW_TWSE,
        qty=qty,
        price=price,
        trade_date=date(2026, 5, 1),
    )
    await db_session.commit()


async def test_record_cash_dividend_happy_path(
    db_session: AsyncSession,
) -> None:
    """CASH dividend records a row AND adds net_amount to realized_pnl."""
    user = await _mk_user(db_session, "s1@x.com", "s1")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    row = await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        pay_date=date(2026, 6, 1),
        amount_per_share=Decimal("5"),
        quantity_at_record=Decimal("100"),
        withholding_tax=Decimal("50"),
    )
    await db_session.commit()

    assert row.id is not None
    assert row.dividend_type == "CASH"
    # Pull the position row from the trade service to confirm realized_pnl
    # accrued: net_amount = 100*5 - 50 = 450.
    trade_svc = PortfolioTradeService(db_session, user)
    pos = await trade_svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos is not None
    # No SELL → realized started at 0, dividend added 450.
    assert pos.realized_pnl == Decimal("450")
    # Quantity / avg_cost untouched by CASH dividend.
    assert pos.quantity == Decimal("100")
    assert pos.avg_cost_fifo == Decimal("500")


async def test_record_stock_dividend_happy_path(
    db_session: AsyncSession,
) -> None:
    """STOCK dividend at 25% scales 100 shares @ 500 → 125 @ 400.

    Ratio 0.25 produces clean Decimal arithmetic so the position
    quantity / avg_cost / total cost preservation can be asserted
    exactly. See `..._preserves_lot_total_cost_invariant` for the
    multi-lot per-lot invariant assertion.
    """
    user = await _mk_user(db_session, "s2@x.com", "s2")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    row = await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="STOCK",
        ex_dividend_date=date(2026, 5, 10),
        quantity_at_record=Decimal("100"),
        ratio=Decimal("0.25"),
    )
    await db_session.commit()

    assert row.dividend_type == "STOCK"
    assert "ratio=0.25" in (row.note or "")
    trade_svc = PortfolioTradeService(db_session, user)
    pos = await trade_svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos is not None
    # 100 * 1.25 = 125
    assert pos.quantity == Decimal("125")
    # 500 / 1.25 = 400 — clean Decimal, no precision loss.
    new_avg = pos.avg_cost_fifo
    assert new_avg is not None
    assert new_avg == Decimal("400")
    # Total cost preserved: 100*500 == 125*400 == 50000
    assert pos.quantity * new_avg == Decimal("50000")


async def test_record_stock_dividend_preserves_lot_total_cost_invariant(
    db_session: AsyncSession,
) -> None:
    """Multi-lot STOCK dividend: every lot's total cost (qty * cost) is
    preserved through the scaling. This is the core domain invariant
    from `dividend_processor`."""
    user = await _mk_user(db_session, "s3@x.com", "s3")
    acc_id = await _seed_account(db_session, user)
    # Build TWO lots via separate BUYs.
    trade_svc = PortfolioTradeService(db_session, user)
    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("10"),
        price=Decimal("100"),
        trade_date=date(2026, 5, 1),
    )
    await trade_svc.record_trade(
        account_id=acc_id,
        action="BUY",
        symbol="X",
        market=Market.TW_TWSE,
        qty=Decimal("20"),
        price=Decimal("200"),
        trade_date=date(2026, 5, 2),
    )
    await db_session.commit()

    # Snapshot per-lot total cost BEFORE.
    pre_lots = await trade_svc._lot_repo.list_open_for_position(
        account_id=acc_id, symbol="X", market=Market.TW_TWSE
    )
    pre_totals = {lot.id: lot.remaining_qty * lot.cost_per_unit for lot in pre_lots}

    svc = PortfolioDividendService(db_session, user)
    await svc.record_dividend(
        account_id=acc_id,
        symbol="X",
        market=Market.TW_TWSE,
        dividend_type="STOCK",
        ex_dividend_date=date(2026, 5, 10),
        quantity_at_record=Decimal("30"),
        # Use 0.25 (scale 1.25) so Decimal division is exact at 8 dp —
        # the per-lot invariant test must hold with bit-perfect equality,
        # not "approximately". Non-clean ratios like 0.1 / 0.5 are
        # legitimate inputs that the domain handles but suffer rounding
        # loss when materialized through Numeric(24, 8); a separate test
        # could relax the bound to ε, but for Phase 2 MVP we lock the
        # invariant only against exact ratios.
        ratio=Decimal("0.25"),
    )
    await db_session.commit()

    post_lots = await trade_svc._lot_repo.list_open_for_position(
        account_id=acc_id, symbol="X", market=Market.TW_TWSE
    )
    for lot in post_lots:
        post_total = lot.remaining_qty * lot.cost_per_unit
        assert post_total == pre_totals[lot.id], (
            f"lot {lot.id} total cost drifted: {post_total} != {pre_totals[lot.id]}"
        )


async def test_record_dividend_tier_blocked_free_user(
    db_session: AsyncSession,
) -> None:
    """FREE tier: dividends feature is false → TierFeatureUnavailable."""
    user = await _mk_user(db_session, "s4@x.com", "s4", tier=UserTier.FREE)
    acc_id = await _seed_account(db_session, user)
    # Need a real position for the CASH path to mean something, but the
    # tier guard is asserted BEFORE we hit the position layer.
    svc = PortfolioDividendService(db_session, user)
    with patch("app.services.portfolio.dividend_service.settings") as s:
        s.enable_monetization = True
        with pytest.raises(TierFeatureUnavailable) as exc:
            await svc.record_dividend(
                account_id=acc_id,
                symbol="2330",
                market=Market.TW_TWSE,
                dividend_type="CASH",
                ex_dividend_date=date(2026, 5, 10),
                amount_per_share=Decimal("5"),
                quantity_at_record=Decimal("100"),
            )
        assert exc.value.feature == "dividends"


async def test_record_dividend_basic_user_passes(
    db_session: AsyncSession,
) -> None:
    """BASIC tier has dividends=true → recording succeeds with monetization on."""
    user = await _mk_user(db_session, "s5@x.com", "s5", tier=UserTier.BASIC)
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    with patch("app.services.portfolio.dividend_service.settings") as s:
        s.enable_monetization = True
        row = await svc.record_dividend(
            account_id=acc_id,
            symbol="2330",
            market=Market.TW_TWSE,
            dividend_type="CASH",
            ex_dividend_date=date(2026, 5, 10),
            amount_per_share=Decimal("2"),
            quantity_at_record=Decimal("100"),
        )
    await db_session.commit()
    assert row.id is not None


async def test_record_dividend_pro_user_passes(
    db_session: AsyncSession,
) -> None:
    """PRO tier has dividends=true → recording succeeds."""
    user = await _mk_user(db_session, "s6@x.com", "s6", tier=UserTier.PRO)
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    with patch("app.services.portfolio.dividend_service.settings") as s:
        s.enable_monetization = True
        row = await svc.record_dividend(
            account_id=acc_id,
            symbol="2330",
            market=Market.TW_TWSE,
            dividend_type="CASH",
            ex_dividend_date=date(2026, 5, 10),
            amount_per_share=Decimal("3"),
            quantity_at_record=Decimal("100"),
        )
    await db_session.commit()
    assert row.id is not None


async def test_record_dividend_unknown_account_raises_404(
    db_session: AsyncSession,
) -> None:
    """Recording against a non-existent account id → PortfolioAccountNotFound."""
    user = await _mk_user(db_session, "s7@x.com", "s7")
    svc = PortfolioDividendService(db_session, user)
    with pytest.raises(PortfolioAccountNotFound):
        await svc.record_dividend(
            account_id=999_999,
            symbol="2330",
            market=Market.TW_TWSE,
            dividend_type="CASH",
            ex_dividend_date=date(2026, 5, 10),
            amount_per_share=Decimal("1"),
            quantity_at_record=Decimal("1"),
        )


async def test_record_dividend_cross_user_rejected(
    db_session: AsyncSession,
) -> None:
    """User B cannot record / read / patch / delete dividends on User A's
    account — 3-attack pattern matching the trade service tests."""
    a = await _mk_user(db_session, "s8a@x.com", "s8a")
    b = await _mk_user(db_session, "s8b@x.com", "s8b")
    acc_a = await _seed_account(db_session, a)
    await _seed_position(db_session, a, acc_a)

    svc_a = PortfolioDividendService(db_session, a)
    svc_b = PortfolioDividendService(db_session, b)

    row = await svc_a.record_dividend(
        account_id=acc_a,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        amount_per_share=Decimal("1"),
        quantity_at_record=Decimal("100"),
    )
    await db_session.commit()

    # Attack 1: B records dividend on A's account.
    with pytest.raises(PortfolioAccountNotFound):
        await svc_b.record_dividend(
            account_id=acc_a,
            symbol="2330",
            market=Market.TW_TWSE,
            dividend_type="CASH",
            ex_dividend_date=date(2026, 5, 11),
            amount_per_share=Decimal("1"),
            quantity_at_record=Decimal("100"),
        )
    # Attack 2: B reads A's dividend.
    with pytest.raises(PortfolioDividendNotFoundError):
        await svc_b.get_dividend(row.id)
    # Attack 3: B deletes A's dividend.
    with pytest.raises(PortfolioDividendNotFoundError):
        await svc_b.delete_dividend(row.id)

    # A's row still intact.
    still = await svc_a.get_dividend(row.id)
    assert still.id == row.id


async def test_audit_log_written_on_record_dividend(
    db_session: AsyncSession,
) -> None:
    """Every CASH/STOCK record emits `portfolio_dividend_recorded`."""
    user = await _mk_user(db_session, "s9@x.com", "s9")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        amount_per_share=Decimal("1"),
        quantity_at_record=Decimal("100"),
    )
    await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="STOCK",
        ex_dividend_date=date(2026, 5, 11),
        quantity_at_record=Decimal("100"),
        ratio=Decimal("0.05"),
    )
    await db_session.commit()
    assert await _count_audit(db_session, "portfolio_dividend_recorded", user.id) == 2


async def test_update_dividend_immutable_field_raises(
    db_session: AsyncSession,
) -> None:
    """PATCH attempts on amount_per_share / dividend_type / quantity_at_record
    raise ValueError (Phase 2 MVP — modify amount = delete + recreate)."""
    user = await _mk_user(db_session, "s10@x.com", "s10")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    row = await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        amount_per_share=Decimal("1"),
        quantity_at_record=Decimal("100"),
    )
    await db_session.commit()

    # Allowed PATCH succeeds.
    updated = await svc.update_dividend(row.id, note="annotated")
    await db_session.commit()
    assert updated.note == "annotated"

    # Immutable PATCH raises.
    with pytest.raises(ValueError, match="immutable"):
        await svc.update_dividend(row.id, amount_per_share=Decimal("99"))
    with pytest.raises(ValueError, match="immutable"):
        await svc.update_dividend(row.id, dividend_type="STOCK")


async def test_delete_dividend_simple_delete_no_rebuild(
    db_session: AsyncSession,
) -> None:
    """delete_dividend removes the row but does NOT reverse the cost-basis
    side effect (Phase 2 MVP). The realized_pnl accrued by the CASH
    dividend remains on the position after delete."""
    user = await _mk_user(db_session, "s11@x.com", "s11")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    row = await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        amount_per_share=Decimal("5"),
        quantity_at_record=Decimal("100"),
    )
    await db_session.commit()

    trade_svc = PortfolioTradeService(db_session, user)
    pos_before = await trade_svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos_before is not None
    realized_before_delete = pos_before.realized_pnl
    assert realized_before_delete == Decimal("500")

    await svc.delete_dividend(row.id)
    await db_session.commit()

    # Row is gone.
    with pytest.raises(PortfolioDividendNotFoundError):
        await svc.get_dividend(row.id)

    # Position's realized_pnl is unchanged (no rebuild).
    pos_after = await trade_svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos_after is not None
    assert pos_after.realized_pnl == realized_before_delete

    # Audit emitted.
    assert await _count_audit(db_session, "portfolio_dividend_deleted", user.id) == 1


# ── A2 semantic confirmation: cash dividend realized_pnl_delta == net_amount
# (already exercised by `test_record_cash_dividend_happy_path`; this case
# locks in the API contract specifically for partial-tax edge case.) ─────────


async def test_record_cash_dividend_zero_withholding_equals_total(
    db_session: AsyncSession,
) -> None:
    """When withholding_tax=0, realized_pnl_delta == total_amount."""
    user = await _mk_user(db_session, "s12@x.com", "s12")
    acc_id = await _seed_account(db_session, user)
    await _seed_position(db_session, user, acc_id)

    svc = PortfolioDividendService(db_session, user)
    await svc.record_dividend(
        account_id=acc_id,
        symbol="2330",
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=date(2026, 5, 10),
        amount_per_share=Decimal("3"),
        quantity_at_record=Decimal("100"),
        # default withholding_tax = 0
    )
    await db_session.commit()
    trade_svc = PortfolioTradeService(db_session, user)
    pos = await trade_svc._position_repo.get(acc_id, "2330", market=Market.TW_TWSE)
    assert pos is not None
    assert pos.realized_pnl == Decimal("300")  # 3 * 100 - 0
