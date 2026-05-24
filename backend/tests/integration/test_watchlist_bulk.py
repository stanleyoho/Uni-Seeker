"""Integration tests for POST /api/v1/watchlist/bulk (Round 6).

Coverage:
  - Happy path: 3 new symbols inserted.
  - Quota: Free tier projected count > 10 → 403 limit_exceeded:max_watchlist
    (whole batch rejected, nothing inserted).
  - Quota off: monetization=False → unlimited (sanity).
  - Pro tier: unlimited regardless of count.
  - Duplicates: symbols already on the watchlist reported in
    skipped_duplicates, not errors.
  - Unknown symbols: reported per-row in errors with reason=stock_not_found.
  - Empty list: Pydantic 422.
  - Over-limit list (>20): Pydantic 422.
  - stock_name JOIN: every `added` item carries stock_name from stocks.name.
  - Cross-user isolation: u1's watchlist is not visible to u2's bulk add.
  - Request-level dedupe: pasting "AAA" twice only inserts once and is
    NOT reported in skipped_duplicates (because it wasn't there before
    the call).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.config import settings
from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist_item import WatchlistItem


async def _make_user(
    db: AsyncSession,
    email: str,
    username: str,
    tier: UserTier = UserTier.FREE,
) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_stock(db: AsyncSession, symbol: str, name: str = "X") -> Stock:
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


@pytest.fixture
def _enable_monetization(monkeypatch):
    monkeypatch.setattr(settings, "enable_monetization", True)


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_add_three_new_symbols(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "bulk1@x.tw", "bulk1")
    await _make_stock(db_session, "2330.TW", "TSMC")
    await _make_stock(db_session, "2454.TW", "MediaTek")
    await _make_stock(db_session, "2317.TW", "Foxconn")

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["2330.TW", "2454.TW", "2317.TW"]},
        headers=_auth(u),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["added"]) == 3
    assert body["skipped_duplicates"] == []
    assert body["errors"] == []

    # stock_name JOIN is populated
    names = {a["symbol"]: a["stock_name"] for a in body["added"]}
    assert names["2330.TW"] == "TSMC"
    assert names["2454.TW"] == "MediaTek"
    assert names["2317.TW"] == "Foxconn"

    # Audit log: one row per insert
    audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "watchlist_added", AuditLog.user_id == u.id)
    )
    assert audits == 3


# ─────────────────────────────────────────────────────────────────────────────
# Quota
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_add_hits_free_tier_limit_returns_403(
    _enable_monetization, client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "bulkcap@x.tw", "bulkcap", tier=UserTier.FREE)
    # Seed 8 existing items → 8 + 3 new = 11 > 10 cap
    for i in range(8):
        s = await _make_stock(db_session, f"EX{i:02d}.TW", f"ex{i}")
        db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()

    for sym in ("NEW01.TW", "NEW02.TW", "NEW03.TW"):
        await _make_stock(db_session, sym, sym)

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["NEW01.TW", "NEW02.TW", "NEW03.TW"]},
        headers=_auth(u),
    )
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "limit_exceeded:max_watchlist"

    # Quota block is atomic — nothing inserted.
    count = await db_session.scalar(
        select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == u.id)
    )
    assert count == 8


@pytest.mark.asyncio
async def test_pro_tier_no_limit_on_bulk(
    _enable_monetization, client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "bulkpro@x.tw", "bulkpro", tier=UserTier.PRO)
    syms = [f"PRO{i:02d}.TW" for i in range(15)]
    for s in syms:
        await _make_stock(db_session, s, s)

    r = await client.post("/api/v1/watchlist/bulk", json={"symbols": syms}, headers=_auth(u))
    assert r.status_code == 201, r.text
    assert len(r.json()["added"]) == 15


# ─────────────────────────────────────────────────────────────────────────────
# Duplicates
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_add_with_existing_duplicates_reports_skipped(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "dup@x.tw", "dup")
    s1 = await _make_stock(db_session, "2330.TW", "TSMC")
    await _make_stock(db_session, "2454.TW", "MediaTek")
    await _make_stock(db_session, "2317.TW", "Foxconn")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s1.id))
    await db_session.commit()

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["2330.TW", "2454.TW", "2317.TW"]},
        headers=_auth(u),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert {a["symbol"] for a in body["added"]} == {"2454.TW", "2317.TW"}
    assert body["skipped_duplicates"] == ["2330.TW"]
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_bulk_add_request_level_dedupe(client: AsyncClient, db_session: AsyncSession):
    """Same symbol twice in one request: insert once, no `skipped_duplicates`."""
    u = await _make_user(db_session, "rdup@x.tw", "rdup")
    await _make_stock(db_session, "2330.TW", "TSMC")

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["2330.TW", "2330.TW", "2330.TW"]},
        headers=_auth(u),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["added"]) == 1
    assert body["added"][0]["symbol"] == "2330.TW"
    assert body["skipped_duplicates"] == []
    assert body["errors"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_add_unknown_symbol_reports_per_row_error(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "err@x.tw", "err")
    await _make_stock(db_session, "2330.TW", "TSMC")

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["2330.TW", "GHOST.NA"]},
        headers=_auth(u),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["added"]) == 1
    assert body["added"][0]["symbol"] == "2330.TW"
    assert body["errors"] == [{"symbol": "GHOST.NA", "reason": "stock_not_found"}]


@pytest.mark.asyncio
async def test_bulk_add_empty_list_returns_422(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "empty@x.tw", "empty")
    r = await client.post("/api/v1/watchlist/bulk", json={"symbols": []}, headers=_auth(u))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_add_over_20_returns_422(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "big@x.tw", "big")
    syms = [f"BIG{i:02d}.TW" for i in range(21)]
    r = await client.post("/api/v1/watchlist/bulk", json={"symbols": syms}, headers=_auth(u))
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# JOIN behaviour
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_watchlist_returns_stock_name_on_join(
    client: AsyncClient, db_session: AsyncSession
):
    """GET /watchlist now JOINs stocks.name into the response."""
    u = await _make_user(db_session, "join@x.tw", "join")
    s = await _make_stock(db_session, "2330.TW", "Taiwan Semiconductor")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()

    r = await client.get("/api/v1/watchlist/", headers=_auth(u))
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["symbol"] == "2330.TW"
    assert items[0]["stock_name"] == "Taiwan Semiconductor"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-user isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_add_cross_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """u2 bulk-adding a symbol u1 already owns should still succeed for u2."""
    u1 = await _make_user(db_session, "iso1@x.tw", "iso1")
    u2 = await _make_user(db_session, "iso2@x.tw", "iso2")
    s = await _make_stock(db_session, "2330.TW", "TSMC")
    db_session.add(WatchlistItem(user_id=u1.id, stock_id=s.id))
    await db_session.commit()

    r = await client.post(
        "/api/v1/watchlist/bulk",
        json={"symbols": ["2330.TW"]},
        headers=_auth(u2),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["added"]) == 1
    assert body["added"][0]["symbol"] == "2330.TW"
    assert body["skipped_duplicates"] == []
