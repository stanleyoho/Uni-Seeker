"""AuditQueryService — user-facing audit log reader (Round 13).

Owns the *one* business rule for the audit viewer: the 10-day retention
window. The DB still holds older rows (compliance/forensics), but the
``/me/audit-logs`` endpoint clamps to the recent slice so the user UI
matches the privacy promise documented in the settings page.

Layering:
    API endpoint  →  AuditQueryService  →  AuditLogRepo  →  ORM
    (auth check)    (retention clamp)     (user_id WHERE)

The service deliberately does not depend on the User model — it accepts
``user_id`` as a primitive so future system surfaces (admin, support
case lookup) can reuse the same retention math without dragging in the
auth dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.repositories.audit import AuditLogRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.audit_log import AuditLog


# Retention window surfaced to the end-user viewer. The underlying
# audit_logs table holds rows indefinitely for compliance; this constant
# is purely the UI-visible window. Bumping it does NOT trigger any data
# migration — it just exposes more history.
USER_VISIBLE_RETENTION_DAYS = 10


class AuditQueryService:
    """Reads the caller's own audit history with the retention window
    enforced. Construct one per request; the underlying repo is cheap.
    """

    def __init__(self, db: AsyncSession, *, user_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self._repo = AuditLogRepo(db)

    @staticmethod
    def _retention_cutoff() -> datetime:
        """Return the inclusive lower bound on ``created_at`` that the
        viewer is allowed to show. Computed at call time so test-time
        freezegun fixtures work without monkey-patching the service.
        """
        return datetime.now(UTC) - timedelta(days=USER_VISIBLE_RETENTION_DAYS)

    async def list_my_audit_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        event_types: list[str] | None = None,
    ) -> list[AuditLog]:
        """List the caller's audit log entries (newest-first) within the
        10-day viewer window. Cross-user reads are structurally
        impossible because the WHERE on ``user_id`` is applied in the
        repo regardless of input.
        """
        return await self._repo.list_by_user(
            self.user_id,
            limit=limit,
            offset=offset,
            event_types=event_types,
            since=self._retention_cutoff(),
        )

    async def count_my_audit_logs(
        self,
        *,
        event_types: list[str] | None = None,
    ) -> int:
        """Total rows visible to the caller under the same retention
        window — drives ``total_count`` / ``has_more`` in the response.
        """
        return await self._repo.count_by_user(
            self.user_id,
            event_types=event_types,
            since=self._retention_cutoff(),
        )
