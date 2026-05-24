"""Plan 5 T7 — /api/v1/alpha/nba/predictions/today (Pro tier only)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User


@pytest.fixture(autouse=True)
def _force_monetization_on(monkeypatch):
    """require_tier becomes a no-op when enable_monetization is False
    (Plan 4 contract). Force-enable so we can assert tier behavior."""
    monkeypatch.setattr(settings, "enable_monetization", True)


async def _make_user(db: AsyncSession, tier: UserTier, uid: int = 1) -> User:
    user = User(
        email=f"alpha{uid}@test.com",
        hashed_password="x" * 60,
        username=f"alpha{uid}",
        tier=tier,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


MOCK_PREDICTIONS = [
    {
        "game_id": "0022509999",
        "home_team": "Lakers",
        "away_team": "Celtics",
        "win_probability": 0.62,
        "calibrated": True,
        "predicted_spread": -3.5,
        "sharp_signal": "sharp",
        "sharp_side": "home",
        "confidence_tier": "MEDIUM",
    }
]


@pytest.mark.asyncio
async def test_pro_user_gets_predictions(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.PRO, uid=1)
    token = create_access_token(user.id, user.email)
    with patch(
        "app.api.v1.alpha.fetch_nba_predictions_today",
        new_callable=AsyncMock,
        return_value=MOCK_PREDICTIONS,
    ):
        resp = await client.get(
            "/api/v1/alpha/nba/predictions/today",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tier"] == "pro"
    assert isinstance(data["predictions"], list)
    assert len(data["predictions"]) >= 1
    first = data["predictions"][0]
    assert "win_probability" in first
    assert "calibrated" in first
    assert "sharp_signal" in first


@pytest.mark.asyncio
async def test_free_user_gets_403(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.FREE, uid=2)
    token = create_access_token(user.id, user.email)
    resp = await client.get(
        "/api/v1/alpha/nba/predictions/today",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_gets_4xx(client: AsyncClient):
    """HTTPBearer auto_error returns 403; some FastAPI versions return 401.
    Tolerate both."""
    resp = await client.get("/api/v1/alpha/nba/predictions/today")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_response_schema_has_required_fields(client: AsyncClient, db_session: AsyncSession):
    user = await _make_user(db_session, UserTier.PRO, uid=3)
    token = create_access_token(user.id, user.email)
    with patch(
        "app.api.v1.alpha.fetch_nba_predictions_today",
        new_callable=AsyncMock,
        return_value=MOCK_PREDICTIONS,
    ):
        resp = await client.get(
            "/api/v1/alpha/nba/predictions/today",
            headers={"Authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert "date" in body
    assert "predictions" in body
    assert "tier" in body
