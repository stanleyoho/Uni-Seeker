"""13F Holdings Tracker ORM model tests — Phase 1 / UNI-F13-001.

Covers the four new f13_* tables + stocks.cusip patch:

  T01 F13Filer instantiation — confirm NO user_id column (Q2 shared)
  T02 F13Filer cik UNIQUE
  T03 F13UserSubscription UNIQUE (user_id, filer_id)
  T04 F13UserSubscription cascade-delete on user delete
  T05 F13Filing UNIQUE (filer_id, accession_number)
  T06 F13Filing form_type CHECK constraint
  T07 F13Holding cascade-delete on filing delete
  T08 F13Holding put_call CHECK constraint
  T09 F13Holding stock_id nullable for unmapped CUSIPs
  T10 stocks.cusip column added (schema patch)
  T11 relationship: F13Filer.filings ↔ F13Filing.filer
  T12 relationship: F13Filing.holdings ↔ F13Holding.filing

Uses the shared SQLite-in-memory `db_session` fixture from
`tests/conftest.py`. ON DELETE / CHECK semantics on SQLite require
`PRAGMA foreign_keys=ON` — enabled here via the same pattern as the
portfolio model tests.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, UTC
from decimal import Decimal

import pytest
from sqlalchemy import event, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models.institutional import (
    F13Filer,
    F13Filing,
    F13Holding,
    F13UserSubscription,
)
from app.models.enums import UserTier
from app.models.stock import Stock
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


async def _mk_user(db, email: str = "i@x.tw", username: str = "iu") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.PRO
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_filer(
    db, cik: str = "0001067983", name: str = "Berkshire Hathaway",
) -> F13Filer:
    f = F13Filer(cik=cik, name=name)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


async def _mk_filing(
    db,
    filer_id: int,
    accession_number: str = "0001067983-25-000001",
    form_type: str = "13F-HR",
    report_period_end: date = date(2026, 3, 31),
) -> F13Filing:
    f = F13Filing(
        filer_id=filer_id,
        accession_number=accession_number,
        form_type=form_type,
        report_period_end=report_period_end,
        filed_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


def _holding_kwargs(filing_id: int, **overrides) -> dict:
    base = dict(
        filing_id=filing_id,
        cusip="037833100",  # AAPL
        name_of_issuer="APPLE INC",
        value_usd=Decimal("123456789.00"),
    )
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────
# T01 — F13Filer instantiation + NO user_id column (Q2 shared)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_filer_instantiation_no_user_id(db_session):
    f = F13Filer(cik="0001067983", name="Berkshire Hathaway")
    db_session.add(f)
    await db_session.commit()
    await db_session.refresh(f)
    assert f.id is not None
    assert f.cik == "0001067983"
    assert f.name == "Berkshire Hathaway"
    assert f.created_at is not None
    # Q2 decision: filer is shared — no user_id column on the table.
    mapper = inspect(F13Filer)
    column_names = {c.key for c in mapper.columns}
    assert "user_id" not in column_names, (
        "F13Filer must NOT have user_id — filers are shared (Q2)"
    )


# ─────────────────────────────────────────────────────────────────────
# T02 — F13Filer.cik UNIQUE
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_filer_cik_unique(db_session):
    db_session.add(F13Filer(cik="0001067983", name="A"))
    await db_session.commit()
    db_session.add(F13Filer(cik="0001067983", name="B"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# T03 — F13UserSubscription UNIQUE (user_id, filer_id)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_user_subscription_unique_user_filer(db_session):
    u = await _mk_user(db_session, "s3@x.tw", "s3")
    f = await _mk_filer(db_session)
    db_session.add(F13UserSubscription(user_id=u.id, filer_id=f.id))
    await db_session.commit()
    db_session.add(F13UserSubscription(user_id=u.id, filer_id=f.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# T04 — F13UserSubscription cascade-delete on user delete
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_user_subscription_cascade_delete_user(db_session):
    u = await _mk_user(db_session, "s4@x.tw", "s4")
    f = await _mk_filer(db_session)
    db_session.add(F13UserSubscription(user_id=u.id, filer_id=f.id))
    await db_session.commit()
    pre = await db_session.scalar(
        select(func.count()).select_from(F13UserSubscription)
    )
    assert pre == 1
    await db_session.delete(u)
    await db_session.commit()
    db_session.expire_all()
    post = await db_session.scalar(
        select(func.count()).select_from(F13UserSubscription)
    )
    assert post == 0
    # Filer must survive — subscriptions cascade does not touch filers.
    survived = await db_session.scalar(
        select(func.count()).select_from(F13Filer)
    )
    assert survived == 1


# ─────────────────────────────────────────────────────────────────────
# T05 — F13Filing UNIQUE (filer_id, accession_number)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_filing_unique_filer_accession(db_session):
    f = await _mk_filer(db_session)
    await _mk_filing(db_session, f.id, "0001067983-25-000001")
    dup = F13Filing(
        filer_id=f.id,
        accession_number="0001067983-25-000001",
        form_type="13F-HR",
        report_period_end=date(2026, 3, 31),
        filed_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# T06 — F13Filing form_type CHECK constraint
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_filing_form_type_check_constraint(db_session):
    f = await _mk_filer(db_session)
    filer_id = f.id  # snapshot — survives the rollback below
    bad = F13Filing(
        filer_id=filer_id,
        accession_number="0001067983-25-000999",
        form_type="13F-NT",  # not in {13F-HR, 13F-HR/A}
        report_period_end=date(2026, 3, 31),
        filed_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # Amendment 13F-HR/A must succeed
    ok = F13Filing(
        filer_id=filer_id,
        accession_number="0001067983-25-000777",
        form_type="13F-HR/A",
        report_period_end=date(2026, 3, 31),
        filed_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
    )
    db_session.add(ok)
    await db_session.commit()


# ─────────────────────────────────────────────────────────────────────
# T07 — F13Holding cascade-delete on filing delete
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_holding_cascade_delete_filing(db_session):
    f = await _mk_filer(db_session)
    fl = await _mk_filing(db_session, f.id)
    for i in range(3):
        db_session.add(F13Holding(**_holding_kwargs(
            fl.id, cusip=f"03783310{i}",
        )))
    await db_session.commit()
    pre = await db_session.scalar(
        select(func.count()).select_from(F13Holding)
    )
    assert pre == 3
    await db_session.delete(fl)
    await db_session.commit()
    db_session.expire_all()
    post = await db_session.scalar(
        select(func.count()).select_from(F13Holding)
    )
    assert post == 0


# ─────────────────────────────────────────────────────────────────────
# T08 — F13Holding put_call CHECK constraint
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_holding_put_call_check_constraint(db_session):
    f = await _mk_filer(db_session)
    fl = await _mk_filing(db_session, f.id)

    # NULL is OK
    db_session.add(F13Holding(**_holding_kwargs(fl.id, put_call=None)))
    # PUT and CALL are OK
    db_session.add(F13Holding(**_holding_kwargs(
        fl.id, cusip="037833101", put_call="PUT",
    )))
    db_session.add(F13Holding(**_holding_kwargs(
        fl.id, cusip="037833102", put_call="CALL",
    )))
    await db_session.commit()

    # Anything else is rejected
    bad = F13Holding(**_holding_kwargs(
        fl.id, cusip="037833103", put_call="STRADDLE",
    ))
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# ─────────────────────────────────────────────────────────────────────
# T09 — F13Holding.stock_id nullable for unmapped CUSIPs
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f13_holding_unmapped_stock_id_nullable(db_session):
    f = await _mk_filer(db_session)
    fl = await _mk_filing(db_session, f.id)
    # Unmapped CUSIP — stock_id stays NULL, must still persist.
    h = F13Holding(**_holding_kwargs(fl.id, stock_id=None))
    db_session.add(h)
    await db_session.commit()
    await db_session.refresh(h)
    assert h.id is not None
    assert h.stock_id is None


# ─────────────────────────────────────────────────────────────────────
# T10 — stocks.cusip column added (schema patch)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_stocks_cusip_column_added(db_session):
    from app.models.enums import Market
    s = Stock(symbol="AAPL", name="Apple Inc.", market=Market.US_NASDAQ)
    s.cusip = "037833100"
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    assert s.cusip == "037833100"

    # Column must also be present on the mapper, nullable, length 9.
    mapper = inspect(Stock)
    cusip_col = mapper.columns["cusip"]
    assert cusip_col.nullable is True
    assert cusip_col.type.length == 9


# ─────────────────────────────────────────────────────────────────────
# T11 — relationship: F13Filer.filings ↔ F13Filing.filer
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_relationship_filer_filings(db_session):
    f = await _mk_filer(db_session)
    fl1 = await _mk_filing(db_session, f.id, "0001067983-25-000001")
    fl2 = await _mk_filing(
        db_session, f.id, "0001067983-25-000002",
        report_period_end=date(2025, 12, 31),
    )
    await db_session.refresh(f, attribute_names=["filings"])
    assert {x.id for x in f.filings} == {fl1.id, fl2.id}
    await db_session.refresh(fl1, attribute_names=["filer"])
    assert fl1.filer.id == f.id


# ─────────────────────────────────────────────────────────────────────
# T12 — relationship: F13Filing.holdings ↔ F13Holding.filing
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_relationship_filing_holdings(db_session):
    f = await _mk_filer(db_session)
    fl = await _mk_filing(db_session, f.id)
    h1 = F13Holding(**_holding_kwargs(fl.id, cusip="037833100"))
    h2 = F13Holding(**_holding_kwargs(fl.id, cusip="594918104"))  # MSFT
    db_session.add_all([h1, h2])
    await db_session.commit()
    await db_session.refresh(fl, attribute_names=["holdings"])
    assert len(fl.holdings) == 2
    await db_session.refresh(h1, attribute_names=["filing"])
    assert h1.filing.id == fl.id
