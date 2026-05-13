"""Integration tests for tier restrictions on indicators, backtest, valuation endpoints.

Plan 4 Task 6: 為 existing API 加 tier 限制。
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User


@pytest.fixture(autouse=True)
def _enable_monetization(monkeypatch):
    """強制 monetization toggle 開啟，否則 require_tier 會放行所有用戶。"""
    from app.config import settings
    monkeypatch.setattr(settings, "enable_monetization", True)


async def _make_user(db: AsyncSession, email: str, tier: UserTier) -> User:
    user = User(
        email=email,
        hashed_password="x" * 60,
        username=email.replace("@", "_").replace(".", "_"),
    )
    user.tier = tier
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


@pytest.mark.asyncio
async def test_free_user_cannot_access_backtest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session, "free@test.com", UserTier.FREE)
    response = await client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "2330",
            "strategy": "ma_cross",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        headers=_auth(user),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_basic_user_cannot_access_backtest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _make_user(db_session, "basic@test.com", UserTier.BASIC)
    response = await client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "2330",
            "strategy": "ma_cross",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        headers=_auth(user),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_free_user_cannot_calculate_advanced_indicator(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """MACD, KD, Bollinger, OBV require Basic tier."""
    user = await _make_user(db_session, "free2@test.com", UserTier.FREE)
    response = await client.post(
        "/api/v1/indicators/calculate/advanced",
        json={"symbol": "2330", "indicator": "MACD", "params": {}},
        headers=_auth(user),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_basic_user_can_calculate_advanced_indicator(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Basic tier can use advanced indicators (even if data not found)."""
    user = await _make_user(db_session, "basic2@test.com", UserTier.BASIC)
    response = await client.post(
        "/api/v1/indicators/calculate/advanced",
        json={"symbol": "NONEXISTENT", "indicator": "MACD", "params": {}},
        headers=_auth(user),
    )
    # 403 would be a tier failure; 404 means tier passed, stock not found
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_anonymous_user_cannot_calculate_advanced_indicator(
    client: AsyncClient,
) -> None:
    """未登入呼叫進階指標應由 require_auth 拋出 401/403。"""
    response = await client.post(
        "/api/v1/indicators/calculate/advanced",
        json={"symbol": "2330", "indicator": "MACD", "params": {}},
    )
    # HTTPBearer auto_error=True (default) returns 403 when missing token
    # depending on FastAPI version; require_auth uses HTTPBearer() without auto_error=False
    assert response.status_code in (401, 403)
