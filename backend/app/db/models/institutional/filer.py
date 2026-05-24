"""F13Filer ORM — 13F Holdings Tracker Phase 1 / UNI-F13-001.

A 13F-filing institution / fund manager identified by SEC CIK. Shared
across all users (Q2 decision): one CIK = one row, regardless of how
many users subscribe. The user → filer relationship lives in
`f13_user_subscriptions`. No `user_id` column on this table.

`latest_*` columns are denormalized hot-path fields refreshed by the
ingestion service after a successful 13F parse. They let the dashboard
render filer cards without joining `f13_filings` on every render.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.db.models.institutional.filing import F13Filing
    from app.db.models.institutional.subscription import F13UserSubscription


class F13Filer(Base):
    __tablename__ = "f13_filers"
    __table_args__ = (
        UniqueConstraint("cik", name="uq_f13_filers_cik"),
        Index("ix_f13_filers_cik", "cik"),
        Index("ix_f13_filers_name", "name"),
    )

    # non-default fields first (MappedAsDataclass)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # defaulted / nullable fields after
    legal_name: Mapped[str | None] = mapped_column(String(500), default=None)
    latest_total_value_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2), default=None,
    )
    latest_options_notional_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2), default=None,
    )
    latest_filing_date: Mapped[date | None] = mapped_column(Date, default=None)
    latest_position_count: Mapped[int | None] = mapped_column(
        Integer, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationships
    filings: Mapped[list["F13Filing"]] = relationship(
        back_populates="filer",
        cascade="all, delete-orphan",
        init=False,
    )
    subscriptions: Mapped[list["F13UserSubscription"]] = relationship(
        back_populates="filer",
        cascade="all, delete-orphan",
        init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<F13Filer id={self.id} cik={self.cik!r} name={self.name!r}>"
        )
