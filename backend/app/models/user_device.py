"""UserDevice ORM model — login fingerprint registry with soft-block.

Plan 4.5 T2. Each row = one (user, fingerprint) pair. Up to 3 active
(blocked_at IS NULL) rows per user; login flow enforces the cap.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


# Uuid is SQLAlchemy 2.0+ cross-dialect type: native UUID on PostgreSQL,
# CHAR(32) on SQLite, with automatic bind/result conversion.
UUID_TYPE = Uuid(as_uuid=True)


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_hash", name="uq_user_device"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(64))
    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, primary_key=True, init=False, default_factory=uuid.uuid4
    )
    user_agent: Mapped[str | None] = mapped_column(String(500), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), init=False, default=None
    )

    user: Mapped[User] = relationship(back_populates="devices", init=False)
