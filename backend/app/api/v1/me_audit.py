"""Current-user audit log viewer — ``/api/v1/me/audit-logs``.

Spec: Round 13 — Audit logs viewer. User-facing read of the
``audit_logs`` table, scoped structurally to the caller's own rows and
clamped to the 10-day visible window by ``AuditQueryService``.

Why a dedicated ``/me/audit-logs`` router rather than reusing
``/notifications`` or a generic ``/audit``:
    * ``/me/...`` is the established convention in this project for
      self-scoped reads (see ``me_notifications.py``).
    * ``/audit`` will eventually host admin-facing forensic search
      (cross-user, no retention clamp) and must NOT alias to the
      self-scoped viewer.

Writes go nowhere through this surface — the only mutation path into
``audit_logs`` remains ``app.services.audit.log_audit_event`` so the
metrics/Sentry breadcrumb side-effects stay co-located with the write.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import require_auth
from app.models.user import User
from app.schemas.audit import AuditLogEntry, AuditLogListResponse
from app.services.audit_query_service import AuditQueryService

router = APIRouter(prefix="/me/audit-logs", tags=["me.audit"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.get(
    "",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_my_audit_logs(
    db: DbDep,
    user: UserDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=500,
            description=(
                "Page size. Hard cap of 500 protects the JSON payload "
                "from accidentally pulling the full retention window."
            ),
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Pagination offset (rows to skip)."),
    ] = 0,
    event_types: Annotated[
        list[str] | None,
        Query(
            description=(
                "Optional whitelist of event_type values to include "
                "(e.g. ``watchlist_added``). Multi-value query param: "
                "``?event_types=user_login&event_types=watchlist_added``."
            ),
        ),
    ] = None,
) -> AuditLogListResponse:
    """List the caller's audit log entries (newest-first, last 10 days).

    Structural isolation: the underlying ``AuditQueryService`` always
    filters by ``user.id`` regardless of any input parameter, so there
    is no path through this endpoint that can return another user's
    rows. The retention clamp (10 days) is enforced server-side.
    """
    service = AuditQueryService(db, user_id=user.id)

    rows = await service.list_my_audit_logs(
        limit=limit, offset=offset, event_types=event_types
    )
    total = await service.count_my_audit_logs(event_types=event_types)

    entries = [AuditLogEntry.from_orm_row(r) for r in rows]
    has_more = offset + len(entries) < total

    return AuditLogListResponse(
        entries=entries,
        total_count=total,
        has_more=has_more,
    )
