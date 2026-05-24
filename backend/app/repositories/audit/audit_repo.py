"""AuditLogRepo — read-only queries over the ``audit_logs`` table.

The audit viewer is a *user-facing* read surface — every method is
scoped by ``user_id`` and orders by ``created_at DESC`` so the freshest
event is the first row returned.

Why no write method here:
    Writes go through ``app.services.audit.log_audit_event`` so the
    Prometheus counter + Sentry breadcrumb side-effects stay in one
    place. This repo deliberately exposes *only* reads to keep that
    invariant unforgeable from the API layer.

Why repository terms rather than reusing the model field names
(``action``, ``event_metadata``) in the public method signature:
    The migration UNI-COMP-001 named the DB column ``action`` (legacy
    Plan 4.5 vocabulary) but the user-facing audit viewer surfaces
    ``event_type`` per Round 13 spec. The repo keeps the SQLAlchemy
    column reference internal — callers pass ``event_types: list[str]``
    and we map them onto ``AuditLog.action`` here.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.audit_log import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuditLogRepo:
    """Read-only repo over ``audit_logs``. User isolation enforced by
    a required ``user_id`` parameter on every method.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        event_types: list[str] | None = None,
        since: datetime | None = None,
    ) -> list[AuditLog]:
        """Return the user's audit logs newest-first.

        Args:
            user_id:     Subject of the audit events. WHERE clause is
                         applied directly so cross-user reads are
                         structurally impossible.
            limit:       Page size cap. Caller (API layer) enforces the
                         tier-driven ceiling; this repo just trusts it.
            offset:      Pagination offset.
            event_types: If non-empty, restrict to these ``action``
                         values (whitelist filter).
            since:       If provided, only events at-or-after this UTC
                         timestamp. Used by the service layer to enforce
                         the 10-day retention window.

        Returns:
            List of AuditLog ORM rows ordered by ``created_at DESC``.
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            # Tiebreak by ``id`` so the page boundary is stable even
            # when multiple events share the same ``created_at`` second
            # (common on SQLite tests where ``func.now()`` returns
            # whole-second granularity). UUID id is random but stable
            # per row, so the ordering is deterministic per-DB.
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if event_types:
            stmt = stmt.where(AuditLog.action.in_(event_types))
        if since is not None:
            stmt = stmt.where(AuditLog.created_at >= since)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: int,
        *,
        event_types: list[str] | None = None,
        since: datetime | None = None,
    ) -> int:
        """Return the total count of rows matching the same filters as
        ``list_by_user`` — used to drive the ``has_more`` /
        ``total_count`` fields in the API response.
        """
        stmt = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.user_id == user_id)
        )
        if event_types:
            stmt = stmt.where(AuditLog.action.in_(event_types))
        if since is not None:
            stmt = stmt.where(AuditLog.created_at >= since)

        result = await self.db.execute(stmt)
        return int(result.scalar_one())
