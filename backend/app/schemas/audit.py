"""DTOs for the ``/api/v1/me/audit-logs`` viewer (Round 13).

Naming reconciliation:
    The DB column is ``action`` (legacy Plan 4.5) and the JSONB sidecar
    is ``event_metadata``. The user-facing API renames them to
    ``event_type`` and ``metadata`` because the Round 13 spec and the
    frontend table headers say so. The mapping is centralised in
    ``AuditLogEntry.from_orm_row`` so the only place that knows about
    the legacy column names is this file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.audit_log import AuditLog


class AuditLogEntry(BaseModel):
    """One row in the audit viewer table.

    ``id`` is returned as a string because the underlying column is a
    UUID — JSON has no canonical UUID type, and the frontend treats it
    as an opaque row key. Numeric ids would break the moment we ever
    backfill a row from a non-monotonic source.
    """

    id: str = Field(description="Audit log row id (UUID).")
    event_type: str = Field(
        description=(
            "Short verb describing the event (e.g. ``user_login``, "
            "``watchlist_added``). Mirrors the ``action`` DB column."
        ),
    )
    resource_type: str | None = Field(
        default=None,
        description="Optional resource entity name (e.g. ``user_device``).",
    )
    resource_id: str | None = Field(
        default=None,
        description="Optional resource identifier as a string.",
    )
    after_state: dict[str, Any] | None = Field(
        default=None,
        description="JSON snapshot of the resource AFTER the event.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Free-form JSON metadata (request fingerprint, ip, …). "
            "Mirrors the ``event_metadata`` DB column."
        ),
    )
    created_at: datetime = Field(
        description="UTC timestamp the event was recorded.",
    )
    # DRIFT-DEMO-DELETE-ME: deliberately add a field without regen'ing
    # the frontend schema.d.ts. The schema-gate workflow should detect
    # the drift and fail this PR.
    drift_demo_field: str = Field(
        default="demo",
        description="E2E-1 drift demo field — DELETE before merging.",
    )

    @classmethod
    def from_orm_row(cls, row: AuditLog) -> AuditLogEntry:
        """Map the ORM row's legacy column names onto the viewer
        contract. Centralised here so the rename only lives in one
        place — handlers stay generic.
        """
        return cls(
            id=str(row.id),
            event_type=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            after_state=row.after_state,
            metadata=row.event_metadata,
            created_at=row.created_at,
        )


class AuditLogListResponse(BaseModel):
    """GET ``/api/v1/me/audit-logs`` envelope.

    Why a wrapped envelope rather than a bare list:
        We need to surface ``total_count`` for the paginator UI and
        ``has_more`` so the client doesn't have to compare
        ``len(entries)`` against ``limit`` to decide whether to enable
        a "next page" button. Both are cheap server-side and would be
        repeatedly re-derived on the client otherwise.
    """

    entries: list[AuditLogEntry] = Field(
        description="Audit log rows ordered by ``created_at DESC``.",
    )
    total_count: int = Field(
        description=(
            "Total number of rows matching the same filter, within the "
            "10-day viewer retention window. Independent of "
            "``limit``/``offset``."
        ),
    )
    has_more: bool = Field(
        description=(
            "True if ``offset + len(entries) < total_count`` — i.e. "
            "another page exists. Pre-computed server-side so the "
            "client doesn't have to."
        ),
    )
