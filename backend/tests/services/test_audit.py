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


# ── Plan 8 T12: Sentry breadcrumb emission ───────────────────────────────────


@pytest.mark.asyncio
async def test_audit_emits_sentry_breadcrumb(db_session, monkeypatch):
    """log_audit_event() should add a Sentry breadcrumb after DB flush."""
    from unittest.mock import patch

    with patch("app.services.audit.sentry_sdk.add_breadcrumb") as mock_bc:
        from app.services.audit import log_audit_event

        await log_audit_event(
            db_session,
            action="tier_upgrade",
            user_id=42,
            resource_type="user",
            resource_id="42",
            before_state={"tier": "free"},
            after_state={"tier": "pro"},
            metadata={"stripe_event_id": "evt_123"},
        )
    assert mock_bc.called
    kwargs = mock_bc.call_args.kwargs
    assert kwargs["category"] == "audit"
    assert kwargs["message"] == "tier_upgrade"
    assert kwargs["level"] == "info"
    data = kwargs["data"]
    # Allowed
    assert data["user_id"] == 42
    assert data["actor_type"] == "user"
    assert data["resource_type"] == "user"
    assert data["resource_id"] == "42"
    # PII-safe: NO before/after/metadata in breadcrumb data
    assert "before_state" not in data
    assert "after_state" not in data
    assert "metadata" not in data


@pytest.mark.asyncio
async def test_audit_breadcrumb_failure_does_not_break_audit(db_session, monkeypatch):
    """If add_breadcrumb raises, log_audit_event() must still complete + return."""
    from unittest.mock import patch

    from sqlalchemy import func, select

    from app.models.audit_log import AuditLog

    with patch(
        "app.services.audit.sentry_sdk.add_breadcrumb",
        side_effect=RuntimeError("sentry down"),
    ):
        from app.services.audit import log_audit_event

        # Must NOT raise
        log = await log_audit_event(
            db_session,
            action="device_added",
            user_id=99,
        )
    # DB row still written
    assert log.id is not None
    count = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "device_added")
    )
    assert count >= 1
