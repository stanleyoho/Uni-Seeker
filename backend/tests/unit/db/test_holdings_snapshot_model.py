"""Holdings snapshot ORM tests — Portfolio Tracker Phase 5 / UNI-PORT-003.

Covers `holdings_snapshots`:
  S01 instantiation w/ required fields
  S02 unique constraint on (user_id, account_id, snapshot_date)
  S03 user-wide row with account_id=NULL coexists with per-account row
  S04 ON DELETE CASCADE — deleting account cascades to its snapshots
  S05 ON DELETE CASCADE — deleting user cascades to all their snapshots
  S06 CHECK constraints: total_value >= 0, position_count >= 0
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models.portfolio import (
    HoldingsSnapshot,
    PortfolioAccount,
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


async def _mk_user(db, email: str = "s@x.tw", username: str = "su") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.PRO
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_account(
    db,
    user_id: int,
    name: str = "SnapMain",
    market: Market = Market.TW_TWSE,
) -> PortfolioAccount:
    acc = PortfolioAccount(user_id=user_id, name=name, market=market)
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


def _snap_kwargs(user_id: int, **overrides) -> dict:
    base = {
        "user_id": user_id,
        "snapshot_date": date(2026, 5, 19),
        "total_value": Decimal("100000.00"),
        "total_cost": Decimal("90000.00"),
        "total_unrealized_pnl": Decimal("10000.00"),
        "realized_pnl_cum": Decimal("0"),
        "position_count": 3,
    }
    base.update(overrides)
    return base


# S01 — instantiation
@pytest.mark.asyncio
async def test_S01_snapshot_instantiation(db_session):
    u = await _mk_user(db_session)
    acc = await _mk_account(db_session, u.id)
    row = HoldingsSnapshot(**_snap_kwargs(u.id, account_id=acc.id))
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.id is not None
    assert row.user_id == u.id
    assert row.account_id == acc.id
    assert row.snapshot_date == date(2026, 5, 19)
    assert row.total_value == Decimal("100000.00")
    assert row.position_count == 3
    assert row.created_at is not None


# S02 — unique constraint
@pytest.mark.asyncio
async def test_S02_unique_constraint_user_account_date(db_session):
    u = await _mk_user(db_session, "s2@x.tw", "s2")
    acc = await _mk_account(db_session, u.id)
    row1 = HoldingsSnapshot(**_snap_kwargs(u.id, account_id=acc.id))
    db_session.add(row1)
    await db_session.commit()
    row2 = HoldingsSnapshot(**_snap_kwargs(u.id, account_id=acc.id))
    db_session.add(row2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# S03 — user-wide row (account_id=NULL) coexists with per-account row
@pytest.mark.asyncio
async def test_S03_user_wide_row_coexists_with_per_account(db_session):
    u = await _mk_user(db_session, "s3@x.tw", "s3")
    acc = await _mk_account(db_session, u.id)
    db_session.add(HoldingsSnapshot(**_snap_kwargs(u.id, account_id=acc.id)))
    db_session.add(HoldingsSnapshot(**_snap_kwargs(u.id, account_id=None)))
    await db_session.commit()
    cnt = await db_session.scalar(select(func.count()).select_from(HoldingsSnapshot))
    assert cnt == 2


# S04 — CASCADE on account delete
@pytest.mark.asyncio
async def test_S04_cascade_delete_account_removes_snapshots(db_session):
    u = await _mk_user(db_session, "s4@x.tw", "s4")
    acc = await _mk_account(db_session, u.id)
    for i in range(3):
        db_session.add(
            HoldingsSnapshot(
                **_snap_kwargs(
                    u.id,
                    account_id=acc.id,
                    snapshot_date=date(2026, 5, 10 + i),
                )
            )
        )
    await db_session.commit()
    pre = await db_session.scalar(select(func.count()).select_from(HoldingsSnapshot))
    assert pre == 3
    await db_session.delete(acc)
    await db_session.commit()
    db_session.expire_all()
    post = await db_session.scalar(select(func.count()).select_from(HoldingsSnapshot))
    assert post == 0


# S05 — CASCADE on user delete (covers user-wide rows too)
@pytest.mark.asyncio
async def test_S05_cascade_delete_user_removes_user_wide_snapshots(db_session):
    u = await _mk_user(db_session, "s5@x.tw", "s5")
    db_session.add(HoldingsSnapshot(**_snap_kwargs(u.id, account_id=None)))
    await db_session.commit()
    pre = await db_session.scalar(select(func.count()).select_from(HoldingsSnapshot))
    assert pre == 1
    await db_session.delete(u)
    await db_session.commit()
    db_session.expire_all()
    post = await db_session.scalar(select(func.count()).select_from(HoldingsSnapshot))
    assert post == 0


# S06 — CHECK constraints
@pytest.mark.asyncio
async def test_S06_check_total_value_nonneg(db_session):
    u = await _mk_user(db_session, "s6a@x.tw", "s6a")
    bad = HoldingsSnapshot(
        **_snap_kwargs(
            u.id,
            account_id=None,
            total_value=Decimal("-1"),
        )
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_S07_check_position_count_nonneg(db_session):
    u = await _mk_user(db_session, "s6b@x.tw", "s6b")
    bad = HoldingsSnapshot(
        **_snap_kwargs(
            u.id,
            account_id=None,
            position_count=-1,
        )
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
