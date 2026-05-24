"""Plan 4.5 T5 integration tests — POST /api/v1/onboarding/kyc."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User


async def _make_user(db: AsyncSession, email: str, username: str) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


@pytest.mark.asyncio
async def test_kyc_conservative_tier(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc1@x.tw", "kyc1")
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [1, 1, 2, 2, 2], "terms_version": "v2026.05.14"},
        headers=_auth(u),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"risk_tolerance": "conservative"}


@pytest.mark.asyncio
async def test_kyc_moderate_tier(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc2@x.tw", "kyc2")
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [3, 3, 3, 3, 3], "terms_version": "v2026.05.14"},
        headers=_auth(u),
    )
    assert r.status_code == 200
    assert r.json()["risk_tolerance"] == "moderate"


@pytest.mark.asyncio
async def test_kyc_aggressive_tier(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc3@x.tw", "kyc3")
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [5, 5, 5, 5, 5], "terms_version": "v2026.05.14"},
        headers=_auth(u),
    )
    assert r.status_code == 200
    assert r.json()["risk_tolerance"] == "aggressive"


@pytest.mark.asyncio
async def test_kyc_writes_audit_log(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc4@x.tw", "kyc4")
    await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [3, 3, 3, 3, 3], "terms_version": "v2026.05.14"},
        headers=_auth(u),
    )
    count = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "kyc_completed")
    )
    assert count == 1
    log = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "kyc_completed"))
    ).one()
    assert log.user_id == u.id
    assert log.after_state == {"risk_tolerance": "moderate"}
    assert log.event_metadata == {"terms_version": "v2026.05.14"}


@pytest.mark.asyncio
async def test_kyc_persists_user_fields(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc5@x.tw", "kyc5")
    await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [4, 4, 4, 4, 4], "terms_version": "v2026.05.14"},
        headers=_auth(u),
    )
    await db_session.refresh(u)
    assert u.risk_tolerance == "aggressive"
    assert u.kyc_completed_at is not None
    assert u.terms_accepted_version == "v2026.05.14"
    assert u.terms_accepted_at is not None


@pytest.mark.asyncio
async def test_kyc_rejects_wrong_length(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc6@x.tw", "kyc6")
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [3, 3, 3], "terms_version": "v"},
        headers=_auth(u),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_kyc_rejects_out_of_range(client: AsyncClient, db_session: AsyncSession):
    u = await _make_user(db_session, "kyc7@x.tw", "kyc7")
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [0, 3, 3, 3, 3], "terms_version": "v"},
        headers=_auth(u),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_kyc_requires_auth(client: AsyncClient):
    r = await client.post(
        "/api/v1/onboarding/kyc",
        json={"answers": [3, 3, 3, 3, 3], "terms_version": "v2026.05.14"},
    )
    assert r.status_code in (401, 403)  # HTTPBearer auto_error → 403
