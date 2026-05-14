import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.services.audit import log_audit_event


@pytest.mark.asyncio
async def test_log_audit_event_minimal(db_session):
    log = await log_audit_event(
        db_session,
        action="kyc_completed",
        user_id=42,
        resource_type="user",
        resource_id="42",
    )
    assert log.id is not None
    assert log.action == "kyc_completed"
    assert log.user_id == 42
    assert log.resource_type == "user"
    assert log.resource_id == "42"

    count = await db_session.scalar(select(func.count()).select_from(AuditLog))
    assert count == 1


@pytest.mark.asyncio
async def test_log_audit_event_with_states(db_session):
    log = await log_audit_event(
        db_session,
        action="device_added",
        user_id=1,
        before_state={"x": 1},
        after_state={"x": 2},
        metadata={"reason": "test", "ip": "1.2.3.4"},
    )
    assert log.before_state == {"x": 1}
    assert log.after_state == {"x": 2}
    assert log.event_metadata == {"reason": "test", "ip": "1.2.3.4"}


@pytest.mark.asyncio
async def test_log_audit_event_actor_type_system(db_session):
    log = await log_audit_event(
        db_session,
        action="device_blocked",
        actor_type="system",
        resource_type="user_device",
    )
    assert log.actor_type == "system"
    assert log.user_id is None


@pytest.mark.asyncio
async def test_log_audit_event_flush_not_commit(db_session):
    """The helper flushes; the caller is responsible for committing."""
    log = await log_audit_event(db_session, action="something")
    # After flush, id should be assigned by the DB default (uuid4)
    assert log.id is not None
    # Rollback should undo it
    await db_session.rollback()
    count = await db_session.scalar(select(func.count()).select_from(AuditLog))
    assert count == 0
