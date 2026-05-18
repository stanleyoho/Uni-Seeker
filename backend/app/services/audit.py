"""Audit logging service — Plan 4.5 minimal stub.

This module exists so call sites in Plan 4.5 (KYC submit, device
registry, device block) can record events into the ``audit_logs`` table.
Plan 7 (Observability) will replace the internals with proper retention
policy, async sink fan-out, and read-model projections. Call sites
remain stable.

Semantics:
- Caller passes plain Python types; we wrap them into an AuditLog row.
- We ``flush`` (not commit) so the caller controls transaction boundary.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.obs.metrics import AUDIT_EVENT_TOTAL


async def log_audit_event(
    db: AsyncSession,
    *,
    action: str,
    user_id: int | None = None,
    actor_type: str = "user",
    resource_type: str | None = None,
    resource_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Insert an AuditLog row and flush; caller commits.

    Args:
        db:            Active AsyncSession.
        action:        Required short verb, e.g. ``"kyc_completed"``.
        user_id:       Subject of the audited action; None for system events.
        actor_type:    ``"user"`` (default) or ``"system"``.
        resource_type: Optional resource entity name, e.g. ``"user_device"``.
        resource_id:   Optional resource identifier as string.
        before_state:  Optional JSON-serializable snapshot before mutation.
        after_state:   Optional JSON-serializable snapshot after mutation.
        metadata:      Optional free-form JSON metadata (fingerprint, ip, ...).

    Returns:
        The flushed AuditLog (id populated). Caller must commit or roll back.
    """
    log = AuditLog(
        action=action,
        actor_type=actor_type,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        event_metadata=metadata,
    )
    db.add(log)
    await db.flush()
    # Plan 8 T5: mirror audit_logs DB rows into Prometheus counter so the
    # observability stack stays in sync with the compliance source of truth.
    AUDIT_EVENT_TOTAL.labels(action=action, actor_type=actor_type).inc()
    return log
