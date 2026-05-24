"""Plan 4.5 T7 — login device fingerprint registry + 3-device limit."""
from datetime import datetime, timezone, UTC

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import _rate_limit_store
from app.auth import hash_password
from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User
from app.models.user_device import UserDevice


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """Login flow has an IP rate-limiter; clear between tests to keep isolation."""
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


async def _register_user(db: AsyncSession, email: str, username: str, password: str = "Password123") -> User:
    u = User(email=email, hashed_password=hash_password(password), username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_first_login_registers_device_and_audits(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _register_user(db_session, "dev1@x.tw", "dev1")
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev1@x.tw", "password": "Password123"},
    )
    assert r.status_code == 200, r.text

    devices = (await db_session.scalars(
        select(UserDevice).where(UserDevice.user_id == u.id)
    )).all()
    assert len(devices) == 1
    assert devices[0].blocked_at is None
    assert devices[0].fingerprint_hash != ""

    audits = (await db_session.scalars(
        select(AuditLog).where(AuditLog.action == "device_added", AuditLog.user_id == u.id)
    )).all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_same_device_relogin_updates_last_seen_no_audit(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _register_user(db_session, "dev2@x.tw", "dev2")
    r1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev2@x.tw", "password": "Password123"},
    )
    assert r1.status_code == 200
    # Capture last_seen after first login
    d = (await db_session.scalars(
        select(UserDevice).where(UserDevice.user_id == u.id)
    )).one()
    first_seen = d.last_seen_at

    # second login with same TestClient → same fingerprint
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev2@x.tw", "password": "Password123"},
    )
    assert r2.status_code == 200

    devices = (await db_session.scalars(
        select(UserDevice).where(UserDevice.user_id == u.id)
    )).all()
    assert len(devices) == 1
    # audit count must still be 1 (no new device_added for relogin)
    audit_count = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "device_added", AuditLog.user_id == u.id
        )
    )
    assert audit_count == 1


@pytest.mark.asyncio
async def test_fourth_device_blocked_with_device_limit_exceeded(
    client: AsyncClient, db_session: AsyncSession
):
    u = await _register_user(db_session, "dev3@x.tw", "dev3")
    # Pre-seed 3 active devices with synthetic fingerprints
    for fp in ("fp_a", "fp_b", "fp_c"):
        db_session.add(UserDevice(user_id=u.id, fingerprint_hash=fp))
    await db_session.commit()

    # 4th login from TestClient (different fingerprint due to UA/IP from httpx)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev3@x.tw", "password": "Password123"},
    )
    assert r.status_code == 403
    body = r.json()
    # Repo wraps detail under `message` via global handler; accept both shapes
    assert body.get("message") == "device_limit_exceeded" or body.get("detail") == "device_limit_exceeded"


@pytest.mark.asyncio
async def test_blocked_device_with_same_fingerprint_rejected(
    client: AsyncClient, db_session: AsyncSession
):
    """If a device row with matching fingerprint exists but is blocked,
    login must fail with `device_blocked`, NOT silently create a new row
    (would violate the unique constraint) and NOT pass the active count
    check (would let blocked attackers in)."""
    u = await _register_user(db_session, "dev4@x.tw", "dev4")
    from types import SimpleNamespace

    from app.services.device import compute_fingerprint
    # We need the fingerprint that the TestClient will produce. Easiest:
    # do one normal login to register it, then mark it blocked.
    r0 = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev4@x.tw", "password": "Password123"},
    )
    assert r0.status_code == 200
    d = (await db_session.scalars(
        select(UserDevice).where(UserDevice.user_id == u.id)
    )).one()
    d.blocked_at = datetime.now(UTC)
    await db_session.commit()

    # Retry login from same TestClient — fingerprint matches blocked row
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev4@x.tw", "password": "Password123"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("message") == "device_blocked" or body.get("detail") == "device_blocked"


@pytest.mark.asyncio
async def test_three_blocked_devices_do_not_count_against_active_limit(
    client: AsyncClient, db_session: AsyncSession
):
    """Blocked devices should not consume the 3-active-device slot,
    so a fresh fingerprint may still register if all existing rows are blocked."""
    u = await _register_user(db_session, "dev5@x.tw", "dev5")
    for fp in ("fp_x", "fp_y", "fp_z"):
        db_session.add(UserDevice(
            user_id=u.id,
            fingerprint_hash=fp,
        ))
    await db_session.commit()
    # Mark all 3 as blocked
    for d in (await db_session.scalars(select(UserDevice).where(UserDevice.user_id == u.id))).all():
        d.blocked_at = datetime.now(UTC)
    await db_session.commit()

    # Login from TestClient produces a different fingerprint than fp_x/y/z → should succeed
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev5@x.tw", "password": "Password123"},
    )
    assert r.status_code == 200
    active = await db_session.scalar(
        select(func.count()).select_from(UserDevice).where(
            UserDevice.user_id == u.id, UserDevice.blocked_at.is_(None)
        )
    )
    assert active == 1
