"""F13UserSubscription ORM — 13F Holdings Tracker Phase 1 / UNI-F13-001.

A user's subscription to a shared `F13Filer`. Drives:
  - the user's "my filers" list on the dashboard
  - tier-limit enforcement (Free 1 / Basic 5 / Pro unlimited — Q5)
  - notify-on-new-filing fan-out (when scheduler arrives in Phase 2)

UNIQUE (user_id, filer_id) — a user cannot subscribe to the same filer
twice. Cascade deletes from both sides: deleting the user removes their
subs; deleting a filer (never happens via UI but migration-safe) removes
all dangling subs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.db.models.institutional.filer import F13Filer


class F13UserSubscription(Base):
    __tablename__ = "f13_user_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "filer_id",
            name="uq_f13_user_subscriptions_user_filer",
        ),
        Index("ix_f13_user_subscriptions_user_id", "user_id"),
        Index("ix_f13_user_subscriptions_filer_id", "filer_id"),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("f13_filers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # defaulted / nullable fields after
    notify_on_new_filing: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )

    filer: Mapped[F13Filer] = relationship(
        back_populates="subscriptions",
        init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<F13UserSubscription id={self.id} user_id={self.user_id} "
            f"filer_id={self.filer_id} notify={self.notify_on_new_filing}>"
        )
