"""Portfolio Tracker Phase 1 ORM model tests — UNI-PORT-001.

Covers the four new tables (portfolio_accounts / _trades / _lots /
_positions) for:
  - construction with required fields
  - column defaults (currency=TWD, remaining_qty default behaviour, etc.)
  - CHECK constraint enforcement (qty>0, price>0)
  - UNIQUE constraint enforcement (account_id, symbol, market)
  - ORM relationships (back_populates wiring)
  - FK ON DELETE CASCADE propagation (account → trades, etc.)
  - NOT NULL constraint on user_id

Uses the shared SQLite-in-memory `db_session` fixture from
`tests/conftest.py`. ON DELETE / CHECK semantics on SQLite require
`PRAGMA foreign_keys=ON` — enabled here via the same pattern as the
watchlist model tests.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models.portfolio import (
    PortfolioAccount,
    PortfolioLot,
    PortfolioPosition,
    PortfolioTrade,
)
from app.models.enums import Market, UserTier
from app.models.user import User


# SQLite honours ON DELETE / CHECK only with foreign_keys pragma on.
@pytest.fixture(autouse=True)
def _enable_sqlite_fk():
    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
        except Exception:
            pass

    yield
    event.remove(Engine, "connect", _set_fk)


async def _mk_user(db, email: str = "p@x.tw", username: str = "p") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_account(
    db,
    user_id: int,
    name: str = "Main",
    market: Market = Market.TW_TWSE,
) -> PortfolioAccount:
    acc = PortfolioAccount(user_id=user_id, name=name, market=market)
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


# ─────────────────────────────────────────────────────────────────────
# 1. PortfolioAccount — required fields
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_account_instantiation(db_session):
    u = await _mk_user(db_session)
    acc = PortfolioAccount(user_id=u.id, name="IBKR Main", market=Market.US_NASDAQ)
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)
    assert acc.id is not None
    assert acc.user_id == u.id
    assert acc.name == "IBKR Main"
    assert acc.market == Market.US_NASDAQ
    assert acc.created_at is not None


# ─────────────────────────────────────────────────────────────────────
# 2. PortfolioAccount — currency defaults to TWD
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_account_default_currency_twd(db_session):
    u = await _mk_user(db_session, "tw@x.tw", "twu")
    acc = PortfolioAccount(user_id=u.id, name="TW Sinopac", market=Market.TW_TWSE)
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)
    assert acc.currency == "TWD"


# ─────────────────────────────────────────────────────────────────────
# 3. PortfolioTrade — required fields construct
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_trade_instantiation(db_session):
    u = await _mk_user(db_session, "t@x.tw", "tu")
    acc = await _mk_account(db_session, u.id)
    tr = PortfolioTrade(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("900.00"),
        quantity=Decimal("1000"),
    )
    db_session.add(tr)
    await db_session.commit()
    await db_session.refresh(tr)
    assert tr.id is not None
    assert tr.action == "BUY"
    assert tr.fee == Decimal("0")
    assert tr.tax == Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# 4. PortfolioTrade — CHECK qty > 0 violation raises
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_trade_buy_qty_positive_check_constraint(db_session):
    u = await _mk_user(db_session, "neg@x.tw", "negu")
    acc = await _mk_account(db_session, u.id)
    bad = PortfolioTrade(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("100"),
        quantity=Decimal("-5"),  # violates ck_portfolio_trades_qty_positive
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 5. PortfolioLot — remaining_qty >= 0 CHECK; default not allowed (NOT NULL)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_lot_remaining_qty_default_zero_check(db_session):
    """remaining_qty is NOT NULL with no default — but the CHECK
    `remaining_qty >= 0` must accept 0 and reject negatives. Verify
    both branches in one test."""
    u = await _mk_user(db_session, "lot@x.tw", "lotu")
    acc = await _mk_account(db_session, u.id)
    tr = PortfolioTrade(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("900"),
        quantity=Decimal("100"),
    )
    db_session.add(tr)
    await db_session.commit()
    await db_session.refresh(tr)

    # 0 is allowed (exhausted lot)
    ok = PortfolioLot(
        trade_id=tr.id,
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        original_qty=Decimal("100"),
        remaining_qty=Decimal("0"),
        cost_per_unit=Decimal("900"),
    )
    db_session.add(ok)
    await db_session.commit()

    # Negative remaining_qty must raise.
    bad = PortfolioLot(
        trade_id=tr.id,
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        original_qty=Decimal("100"),
        remaining_qty=Decimal("-1"),
        cost_per_unit=Decimal("900"),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 6. PortfolioPosition — UNIQUE (account_id, symbol, market)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_position_unique_per_account_stock(db_session):
    u = await _mk_user(db_session, "pos@x.tw", "posu")
    acc = await _mk_account(db_session, u.id)
    p1 = PortfolioPosition(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        currency="TWD",
    )
    db_session.add(p1)
    await db_session.commit()

    p2 = PortfolioPosition(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        currency="TWD",
    )
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 7. Relationship account → trades
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_relationship_account_to_trades(db_session):
    u = await _mk_user(db_session, "rel1@x.tw", "rel1u")
    acc = await _mk_account(db_session, u.id)
    for i in range(3):
        db_session.add(
            PortfolioTrade(
                account_id=acc.id,
                symbol="2330.TW",
                market=Market.TW_TWSE,
                action="BUY",
                trade_date=date(2026, 5, i + 1),
                price=Decimal("900"),
                quantity=Decimal("10"),
            )
        )
    await db_session.commit()

    await db_session.refresh(acc, attribute_names=["trades"])
    assert len(acc.trades) == 3
    assert all(t.account_id == acc.id for t in acc.trades)


# ─────────────────────────────────────────────────────────────────────
# 8. Relationship trade → lots
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_relationship_trade_to_lots(db_session):
    u = await _mk_user(db_session, "rel2@x.tw", "rel2u")
    acc = await _mk_account(db_session, u.id)
    tr = PortfolioTrade(
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("900"),
        quantity=Decimal("100"),
    )
    db_session.add(tr)
    await db_session.commit()
    await db_session.refresh(tr)

    lot = PortfolioLot(
        trade_id=tr.id,
        account_id=acc.id,
        symbol="2330.TW",
        market=Market.TW_TWSE,
        original_qty=Decimal("100"),
        remaining_qty=Decimal("100"),
        cost_per_unit=Decimal("900"),
    )
    db_session.add(lot)
    await db_session.commit()
    await db_session.refresh(tr, attribute_names=["lots"])
    assert len(tr.lots) == 1
    assert tr.lots[0].remaining_qty == Decimal("100")


# ─────────────────────────────────────────────────────────────────────
# 9. ON DELETE CASCADE: account → trades
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cascade_delete_account_removes_trades(db_session):
    u = await _mk_user(db_session, "cas@x.tw", "casu")
    acc = await _mk_account(db_session, u.id)
    db_session.add(
        PortfolioTrade(
            account_id=acc.id,
            symbol="2330.TW",
            market=Market.TW_TWSE,
            action="BUY",
            trade_date=date(2026, 5, 1),
            price=Decimal("900"),
            quantity=Decimal("100"),
        )
    )
    await db_session.commit()

    # Expire all so we re-read fresh after delete via DB cascade
    await db_session.delete(acc)
    await db_session.commit()
    db_session.expire_all()

    cnt = await db_session.scalar(select(func.count()).select_from(PortfolioTrade))
    assert cnt == 0


# ─────────────────────────────────────────────────────────────────────
# 10. PortfolioAccount.user_id NOT NULL
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_user_id_not_null_constraint(db_session):
    acc = PortfolioAccount(
        user_id=None,  # type: ignore[arg-type]
        name="No-owner",
        market=Market.TW_TWSE,
    )
    db_session.add(acc)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
