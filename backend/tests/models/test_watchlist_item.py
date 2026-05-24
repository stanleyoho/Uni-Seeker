"""WatchlistItem ORM model tests — Plan 4 Task 7 / WATCH-001."""

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine

from app.models.enums import Market, UserTier
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist_item import WatchlistItem


# DB-level CASCADE on watchlist_items is defined in the alembic migration
# (Postgres production). SQLite honors ON DELETE CASCADE only when
# PRAGMA foreign_keys=ON; enable it so this test exercises the same
# cascade semantics that production relies on.
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


async def _make_user(db, email: str = "w@x.tw", username: str = "w") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_stock(db, symbol: str = "2330.TW", name: str = "TSMC") -> Stock:
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest.mark.asyncio
async def test_can_create_watchlist_item(db_session):
    u = await _make_user(db_session)
    s = await _make_stock(db_session)
    w = WatchlistItem(user_id=u.id, stock_id=s.id)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    assert w.id is not None
    assert w.user_id == u.id
    assert w.stock_id == s.id
    assert w.created_at is not None


@pytest.mark.asyncio
async def test_unique_user_stock_constraint(db_session):
    u = await _make_user(db_session, "u2@x.tw", "u2")
    s = await _make_stock(db_session, "2454.TW", "MediaTek")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_cascade_delete_on_user_delete(db_session):
    u = await _make_user(db_session, "u3@x.tw", "u3")
    s = await _make_stock(db_session, "2317.TW", "Foxconn")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()
    await db_session.delete(u)
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(WatchlistItem))
    assert count == 0


@pytest.mark.asyncio
async def test_cascade_delete_on_stock_delete(db_session):
    u = await _make_user(db_session, "u4@x.tw", "u4")
    s = await _make_stock(db_session, "2308.TW", "Delta")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()
    await db_session.delete(s)
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(WatchlistItem))
    assert count == 0
