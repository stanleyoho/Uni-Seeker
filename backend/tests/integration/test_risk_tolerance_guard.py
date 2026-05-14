"""Plan 4.5 T6 — require_risk_tolerance guard."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User


async def _user(db: AsyncSession, email: str, username: str, risk: str | None) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    if risk is not None:
        u.risk_tolerance = risk
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


@pytest.mark.asyncio
async def test_no_kyc_blocked_with_kyc_required(client: AsyncClient, db_session: AsyncSession):
    u = await _user(db_session, "rt1@x.tw", "rt1", risk=None)
    r = await client.get("/api/v1/onboarding/risky-demo", headers=_auth(u))
    assert r.status_code == 403
    # Global HTTPException handler maps HTTPException.detail → body["message"].
    body = r.json()
    assert body.get("message") == "kyc_required" or body.get("detail") == "kyc_required"


@pytest.mark.asyncio
async def test_conservative_blocked_with_insufficient(client: AsyncClient, db_session: AsyncSession):
    u = await _user(db_session, "rt2@x.tw", "rt2", risk="conservative")
    r = await client.get("/api/v1/onboarding/risky-demo", headers=_auth(u))
    assert r.status_code == 403
    body = r.json()
    assert (
        body.get("message") == "risk_tolerance_insufficient"
        or body.get("detail") == "risk_tolerance_insufficient"
    )


@pytest.mark.asyncio
async def test_moderate_passes(client: AsyncClient, db_session: AsyncSession):
    u = await _user(db_session, "rt3@x.tw", "rt3", risk="moderate")
    r = await client.get("/api/v1/onboarding/risky-demo", headers=_auth(u))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["user_id"] == u.id


@pytest.mark.asyncio
async def test_aggressive_passes(client: AsyncClient, db_session: AsyncSession):
    u = await _user(db_session, "rt4@x.tw", "rt4", risk="aggressive")
    r = await client.get("/api/v1/onboarding/risky-demo", headers=_auth(u))
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_unauth_returns_4xx(client: AsyncClient):
    r = await client.get("/api/v1/onboarding/risky-demo")
    # HTTPBearer auto_error → 403 (FastAPI default)
    assert r.status_code in (401, 403)
