"""AuditLog ORM model (skeleton; Plan 7 will extend the call-site internals)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Uuid is SQLAlchemy 2.0+ cross-dialect type: native UUID on PostgreSQL,
# CHAR(32) on SQLite, with automatic bind/result conversion.
UUID_TYPE = Uuid(as_uuid=True)
JSONB_TYPE = JSONB().with_variant(JSON, "sqlite")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(100))
    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, init=False, default_factory=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(String(20), default="user")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    resource_type: Mapped[str | None] = mapped_column(String(50), default=None)
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB_TYPE, default=None)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB_TYPE, default=None)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB_TYPE, default=None)
