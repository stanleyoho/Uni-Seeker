"""Plan 5 T8 — /api/v1/alpha/stocks/edge/{stock_id} (Pro tier only)."""

from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User
from app.modules.stock_signals.sharp_detector import EdgeSignal


@pytest.fixture(autouse=True)
def _force_monetization_on(monkeypatch):
    """Same as test_alpha_nba: force tier guard to actually gate."""
    monkeypatch.setattr(settings, "enable_monetization", True)


async def _make_user(db: AsyncSession, tier: UserTier, uid: int = 10) -> User:
    user = User(
        email=f"stocktest{uid}@test.com",
        hashed_password="x" * 60,
        username=f"stocktest{uid}",
        tier=tier,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


MOCK_EDGE = EdgeSignal(
    stock_id="2330",
    date=date(2026, 5, 9),
    direction="long",
    confidence=0.72,
    divergence_detected=True,
    reason=(
        "法人期貨淨部位 +8,000 口（long），融資餘額變化 -40.0 億，"
        "方向相反（divergence=True）。跟隨法人方向，信心度 72%。"
    ),
)


@pytest.mark.asyncio
async def test_pro_user_gets_edge_signal(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.PRO, uid=10)
    token = create_access_token(user.id, user.email)
    with patch(
        "app.api.v1.alpha.fetch_stock_edge_signal",
        return_value=MOCK_EDGE,
    ):
        resp = await client.get(
            "/api/v1/alpha/stocks/edge/2330",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["stock_id"] == "2330"
    assert data["direction"] == "long"
    assert data["divergence_detected"] is True
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["reason"], str)


@pytest.mark.asyncio
async def test_free_user_gets_403(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.FREE, uid=11)
    token = create_access_token(user.id, user.email)
    resp = await client.get(
        "/api/v1/alpha/stocks/edge/2330",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_gets_4xx(client: AsyncClient):
    resp = await client.get("/api/v1/alpha/stocks/edge/2330")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_response_schema_complete(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.PRO, uid=12)
    token = create_access_token(user.id, user.email)
    with patch(
        "app.api.v1.alpha.fetch_stock_edge_signal",
        return_value=MOCK_EDGE,
    ):
        resp = await client.get(
            "/api/v1/alpha/stocks/edge/2330",
            headers={"Authorization": f"Bearer {token}"},
        )
    body = resp.json()
    required_fields = {
        "stock_id",
        "date",
        "direction",
        "confidence",
        "divergence_detected",
        "reason",
        "tier",
    }
    assert required_fields.issubset(body.keys())


@pytest.mark.asyncio
async def test_direction_values_constrained(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.PRO, uid=13)
    token = create_access_token(user.id, user.email)
    with patch(
        "app.api.v1.alpha.fetch_stock_edge_signal",
        return_value=MOCK_EDGE,
    ):
        resp = await client.get(
            "/api/v1/alpha/stocks/edge/2330",
            headers={"Authorization": f"Bearer {token}"},
        )
    direction = resp.json()["direction"]
    assert direction in ("long", "short", "neutral")
