"""Portfolio Tracker Phase 2 ORM model tests — UNI-PORT-002.

Covers `portfolio_dividends`:
  - construction with required fields
  - dividend_type CHECK constraint ('CASH' / 'STOCK' only)
  - amount_per_share > 0 CHECK
  - quantity_at_record > 0 CHECK
  - withholding_tax >= 0 CHECK
  - ON DELETE CASCADE account → dividends
  - account.dividends relationship returns list
  - currency default 'TWD'
  - optional fields (pay_date, note) nullable

Mirrors the Phase 1 test pattern (`tests/unit/db/test_portfolio_models.py`):
shared SQLite-in-memory fixture from `tests/conftest.py`; PRAGMA
foreign_keys=ON enabled per-test for CHECK / CASCADE honoring.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models.portfolio import PortfolioAccount, PortfolioDividend
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


async def _mk_user(db, email: str = "d@x.tw", username: str = "d") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_account(
    db,
    user_id: int,
    name: str = "DivMain",
    market: Market = Market.TW_TWSE,
) -> PortfolioAccount:
    acc = PortfolioAccount(user_id=user_id, name=name, market=market)
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


def _div_kwargs(account_id: int, **overrides) -> dict:
    """Minimal required-field kwargs for a CASH dividend. Override any
    field with **overrides to test edge cases without re-listing the
    common 6 required columns each time."""
    base = {
        "account_id": account_id,
        "symbol": "2330.TW",
        "market": Market.TW_TWSE,
        "dividend_type": "CASH",
        "ex_dividend_date": date(2026, 7, 15),
        "amount_per_share": Decimal("4.00"),
        "quantity_at_record": Decimal("1000"),
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────
# 1. Construction with required fields
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_portfolio_dividend_instantiation(db_session):
    u = await _mk_user(db_session)
    acc = await _mk_account(db_session, u.id)
    d = PortfolioDividend(**_div_kwargs(acc.id))
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    assert d.id is not None
    assert d.account_id == acc.id
    assert d.symbol == "2330.TW"
    assert d.market == Market.TW_TWSE
    assert d.dividend_type == "CASH"
    assert d.ex_dividend_date == date(2026, 7, 15)
    assert d.amount_per_share == Decimal("4.00")
    assert d.quantity_at_record == Decimal("1000")
    assert d.created_at is not None
    assert d.updated_at is not None


# ─────────────────────────────────────────────────────────────────────
# 2. dividend_type CHECK rejects values outside CASH / STOCK
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dividend_type_check_constraint(db_session):
    u = await _mk_user(db_session, "t1@x.tw", "t1")
    acc = await _mk_account(db_session, u.id)
    bad = PortfolioDividend(
        **_div_kwargs(acc.id, dividend_type="BONUS"),  # not in CHECK list
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 3. amount_per_share > 0 CHECK
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_amount_per_share_positive_check(db_session):
    u = await _mk_user(db_session, "t2@x.tw", "t2")
    acc = await _mk_account(db_session, u.id)
    bad = PortfolioDividend(
        **_div_kwargs(acc.id, amount_per_share=Decimal("0")),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 4. quantity_at_record > 0 CHECK
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_quantity_at_record_positive_check(db_session):
    u = await _mk_user(db_session, "t3@x.tw", "t3")
    acc = await _mk_account(db_session, u.id)
    bad = PortfolioDividend(
        **_div_kwargs(acc.id, quantity_at_record=Decimal("-1")),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 5. withholding_tax >= 0 CHECK — accepts 0, rejects negative
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_withholding_tax_non_negative_check(db_session):
    u = await _mk_user(db_session, "t4@x.tw", "t4")
    acc = await _mk_account(db_session, u.id)

    # 0 is allowed (default)
    ok = PortfolioDividend(
        **_div_kwargs(acc.id, withholding_tax=Decimal("0")),
    )
    db_session.add(ok)
    await db_session.commit()

    # negative rejected
    bad = PortfolioDividend(
        **_div_kwargs(acc.id, withholding_tax=Decimal("-0.01")),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# 6. ON DELETE CASCADE: account → dividends
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cascade_delete_account_removes_dividends(db_session):
    u = await _mk_user(db_session, "t5@x.tw", "t5")
    acc = await _mk_account(db_session, u.id)
    for i in range(3):
        db_session.add(
            PortfolioDividend(
                **_div_kwargs(
                    acc.id,
                    ex_dividend_date=date(2026, 6, i + 1),
                ),
            )
        )
    await db_session.commit()

    # Sanity: 3 rows exist
    cnt = await db_session.scalar(select(func.count()).select_from(PortfolioDividend))
    assert cnt == 3

    await db_session.delete(acc)
    await db_session.commit()
    db_session.expire_all()

    cnt = await db_session.scalar(select(func.count()).select_from(PortfolioDividend))
    assert cnt == 0


# ─────────────────────────────────────────────────────────────────────
# 7. account.dividends relationship returns list
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_account_dividends_relationship(db_session):
    u = await _mk_user(db_session, "t6@x.tw", "t6")
    acc = await _mk_account(db_session, u.id)
    for i in range(2):
        db_session.add(
            PortfolioDividend(
                **_div_kwargs(
                    acc.id,
                    ex_dividend_date=date(2026, 6, i + 1),
                    amount_per_share=Decimal(f"{4 + i}.00"),
                ),
            )
        )
    await db_session.commit()
    await db_session.refresh(acc, attribute_names=["dividends"])

    assert len(acc.dividends) == 2
    assert all(d.account_id == acc.id for d in acc.dividends)


# ─────────────────────────────────────────────────────────────────────
# 8. currency default = 'TWD'
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_default_currency_twd(db_session):
    u = await _mk_user(db_session, "t7@x.tw", "t7")
    acc = await _mk_account(db_session, u.id)
    d = PortfolioDividend(**_div_kwargs(acc.id))
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    assert d.currency == "TWD"


# ─────────────────────────────────────────────────────────────────────
# 9. Optional fields (pay_date, note) nullable
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_optional_fields_can_be_null(db_session):
    u = await _mk_user(db_session, "t8@x.tw", "t8")
    acc = await _mk_account(db_session, u.id)
    d = PortfolioDividend(**_div_kwargs(acc.id))  # pay_date / note omitted
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    assert d.pay_date is None
    assert d.note is None

    # And explicitly-supplied None works (no IntegrityError)
    d2 = PortfolioDividend(
        **_div_kwargs(
            acc.id,
            ex_dividend_date=date(2026, 8, 1),
            pay_date=None,
            note=None,
        )
    )
    db_session.add(d2)
    await db_session.commit()
