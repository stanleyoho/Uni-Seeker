"""Integration tests for /api/v1/watchlist — WATCH-001 / Plan 4 Task 7."""

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


# ─────────────────────────────────────────────────────────────────────────────
# Add
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_to_watchlist_creates_row_and_audits(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "add1@x.tw", "add1")
    await _make_stock(db_session, "2330.TW", "TSMC")

    r = await client.post("/api/v1/watchlist/", json={"symbol": "2330.TW"}, headers=_auth(u))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["symbol"] == "2330.TW"
    assert body["id"] is not None
    assert body["created_at"]

    count = await db_session.scalar(
        select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == u.id)
    )
    assert count == 1

    audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "watchlist_added", AuditLog.user_id == u.id)
    )
    assert audits == 1


@pytest.mark.asyncio
async def test_add_unknown_symbol_returns_404(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "unk@x.tw", "unk")
    r = await client.post("/api/v1/watchlist/", json={"symbol": "ABCDEF.NA"}, headers=_auth(u))
    assert r.status_code == 404
    assert r.json()["message"] == "stock_not_found"


@pytest.mark.asyncio
async def test_duplicate_add_returns_409(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "dup@x.tw", "dup")
    await _make_stock(db_session, "2454.TW", "MediaTek")
    r1 = await client.post("/api/v1/watchlist/", json={"symbol": "2454.TW"}, headers=_auth(u))
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/watchlist/", json={"symbol": "2454.TW"}, headers=_auth(u))
    assert r2.status_code == 409
    assert r2.json()["message"] == "watchlist_already_exists"


# ─────────────────────────────────────────────────────────────────────────────
# List
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_watchlist_returns_user_items(client: AsyncClient, db_session: AsyncSession):
    u1 = await _make_user(db_session, "l1@x.tw", "l1")
    u2 = await _make_user(db_session, "l2@x.tw", "l2")
    s1 = await _make_stock(db_session, "2330.TW", "TSMC")
    s2 = await _make_stock(db_session, "2454.TW", "MediaTek")
    s3 = await _make_stock(db_session, "2317.TW", "Foxconn")

    # u1 has 3, u2 has 1 (must be excluded from u1's list)
    db_session.add_all(
        [
            WatchlistItem(user_id=u1.id, stock_id=s1.id),
            WatchlistItem(user_id=u1.id, stock_id=s2.id),
            WatchlistItem(user_id=u1.id, stock_id=s3.id),
            WatchlistItem(user_id=u2.id, stock_id=s1.id),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/v1/watchlist/", headers=_auth(u1))
    assert r.status_code == 200
    symbols = sorted(row["symbol"] for row in r.json())
    assert symbols == ["2317.TW", "2330.TW", "2454.TW"]


# ─────────────────────────────────────────────────────────────────────────────
# Remove
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_from_watchlist_deletes_and_audits(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "del1@x.tw", "del1")
    s = await _make_stock(db_session, "2330.TW", "TSMC")
    db_session.add(WatchlistItem(user_id=u.id, stock_id=s.id))
    await db_session.commit()

    r = await client.delete("/api/v1/watchlist/2330.TW", headers=_auth(u))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    count = await db_session.scalar(
        select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == u.id)
    )
    assert count == 0

    audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "watchlist_removed", AuditLog.user_id == u.id)
    )
    assert audits == 1


@pytest.mark.asyncio
async def test_remove_then_re_add_works(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "redo@x.tw", "redo")
    await _make_stock(db_session, "2330.TW", "TSMC")

    r1 = await client.post("/api/v1/watchlist/", json={"symbol": "2330.TW"}, headers=_auth(u))
    assert r1.status_code == 201
    r2 = await client.delete("/api/v1/watchlist/2330.TW", headers=_auth(u))
    assert r2.status_code == 200
    r3 = await client.post("/api/v1/watchlist/", json={"symbol": "2330.TW"}, headers=_auth(u))
    assert r3.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Free tier 10-item cap (gated on enable_monetization=True)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def _enable_monetization(monkeypatch):
    monkeypatch.setattr(settings, "enable_monetization", True)


@pytest.mark.asyncio
async def test_free_user_at_10_items_cannot_add_11th(
    _enable_monetization, client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "cap@x.tw", "cap", tier=UserTier.FREE)
    stocks = [await _make_stock(db_session, f"CAP{i:02d}.TW", f"cap{i}") for i in range(11)]
    # Seed 10 items
    db_session.add_all([WatchlistItem(user_id=u.id, stock_id=s.id) for s in stocks[:10]])
    await db_session.commit()

    r = await client.post(
        "/api/v1/watchlist/",
        json={"symbol": stocks[10].symbol},
        headers=_auth(u),
    )
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "watchlist_limit_exceeded"


@pytest.mark.asyncio
async def test_pro_user_can_exceed_10(
    _enable_monetization, client: AsyncClient, db_session: AsyncSession
):
    u = await _make_user(db_session, "pro@x.tw", "pro", tier=UserTier.PRO)
    for i in range(12):
        await _make_stock(db_session, f"PRO{i:02d}.TW", f"pro{i}")
        r = await client.post(
            "/api/v1/watchlist/",
            json={"symbol": f"PRO{i:02d}.TW"},
            headers=_auth(u),
        )
        assert r.status_code == 201, f"Pro user blocked at #{i}: {r.text}"


@pytest.mark.asyncio
async def test_free_user_unlimited_when_monetization_off(
    client: AsyncClient, db_session: AsyncSession
):
    """When enable_monetization=False (default), Free users are not capped."""
    # Sanity-check the default; if this changes, the test stays meaningful
    # because monetization_off is the documented dev/test posture.
    assert settings.enable_monetization is False
    u = await _make_user(db_session, "free@x.tw", "free", tier=UserTier.FREE)
    for i in range(11):
        await _make_stock(db_session, f"NOC{i:02d}.TW", f"noc{i}")
        r = await client.post(
            "/api/v1/watchlist/",
            json={"symbol": f"NOC{i:02d}.TW"},
            headers=_auth(u),
        )
        assert r.status_code == 201, f"Free unmetered user blocked at #{i}: {r.text}"


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauth_returns_4xx(client: AsyncClient):
    r = await client.get("/api/v1/watchlist/")
    assert r.status_code in (401, 403)
