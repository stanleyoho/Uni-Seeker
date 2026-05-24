"""Plan 4.5 T8 — block_device helper."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User
from app.models.user_device import UserDevice
from app.services.device import block_device


async def _user_with_device(
    db, email="bd1@x.tw", username="bd1", fp="fp1"
) -> tuple[User, UserDevice]:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    d = UserDevice(user_id=u.id, fingerprint_hash=fp)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return u, d


@pytest.mark.asyncio
async def test_block_device_sets_blocked_at(db_session):
    _, d = await _user_with_device(db_session)
    result = await block_device(db_session, d.id, reason="user_reported")
    assert result is not None
    assert result.id == d.id
    assert result.blocked_at is not None


@pytest.mark.asyncio
async def test_block_device_writes_audit(db_session):
    u, d = await _user_with_device(db_session, "bd2@x.tw", "bd2", "fp2")
    await block_device(db_session, d.id, reason="suspicious_activity")
    audits = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "device_blocked"))
    ).all()
    assert len(audits) == 1
    log = audits[0]
    assert log.user_id == u.id
    assert log.actor_type == "system"
    assert log.resource_type == "user_device"
    assert log.resource_id == str(d.id)
    assert log.event_metadata is not None
    assert log.event_metadata.get("reason") == "suspicious_activity"


@pytest.mark.asyncio
async def test_block_device_actor_type_override(db_session):
    u, d = await _user_with_device(db_session, "bd3@x.tw", "bd3", "fp3")
    await block_device(db_session, d.id, reason="admin_action", actor_type="admin")
    log = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "device_blocked"))
    ).one()
    assert log.actor_type == "admin"


@pytest.mark.asyncio
async def test_block_device_idempotent(db_session):
    """Blocking an already-blocked device should be a no-op (or at least
    not crash). It should still record an audit so admins can trace
    the operator’s intent."""
    _, d = await _user_with_device(db_session, "bd4@x.tw", "bd4", "fp4")
    await block_device(db_session, d.id, reason="first")
    await block_device(db_session, d.id, reason="second")
    audits = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "device_blocked")
    )
    assert audits == 2


@pytest.mark.asyncio
async def test_block_device_returns_none_for_unknown_id(db_session):
    """If the device_id does not exist, return None (do not raise) so the
    caller can decide how to surface the error."""
    fake = uuid.uuid4()
    result = await block_device(db_session, fake, reason="ghost")
    assert result is None
    audits = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "device_blocked")
    )
    assert audits == 0
