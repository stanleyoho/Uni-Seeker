"""Audit log repositories (Round 13 — audit viewer).

CRUD-only layer over ``app.models.audit_log``. Per design spec §11 R3
repos MUST NOT contain business logic; the audit viewer's only
business rule (10-day retention window) lives in the service layer.

Structural user isolation: every read method that touches an audit row
takes a non-optional ``user_id`` and filters by it directly. There is
no method here that can return one user's row to another user.
"""

from app.repositories.audit.audit_repo import AuditLogRepo

__all__ = ["AuditLogRepo"]
