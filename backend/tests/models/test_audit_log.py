import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog


@pytest.mark.asyncio
async def test_audit_log_minimal(db_session):
    log = AuditLog(action="something_happened")
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.id is not None
    assert log.action == "something_happened"
    assert log.actor_type == "user"  # default
    assert log.user_id is None


@pytest.mark.asyncio
async def test_audit_log_with_jsonb(db_session):
    log = AuditLog(
        action="risky_change",
        user_id=42,
        before_state={"v": 1},
        after_state={"v": 2},
        event_metadata={"ip": "1.2.3.4"},
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.before_state == {"v": 1}
    assert log.after_state == {"v": 2}
    assert log.event_metadata == {"ip": "1.2.3.4"}


@pytest.mark.asyncio
async def test_audit_log_actor_type_override(db_session):
    log = AuditLog(action="system_kicked_in", actor_type="system")
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.actor_type == "system"
