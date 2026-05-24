"""F13Filing ORM — 13F Holdings Tracker Phase 1 / UNI-F13-001.

One row per 13F-HR (or 13F-HR/A amendment) submission a filer makes to
the SEC. Each filing carries one `infoTable.xml` parsed into many
`F13Holding` rows.

`total_value_usd` is the sum of `value × 1000` across all holdings
(pure 13F long positions). `options_notional_usd` is the sum across
holdings where `put_call` is non-null. Both are populated at ingest
time (Batch A2) and used by the dashboard to display the (a)+(b) two-
column AUM view per Q3 decision.

UNIQUE (filer_id, accession_number) — re-ingesting the same SEC
accession is idempotent. CHECK on `form_type` to refuse non-13F-HR
forms (e.g. 13F-NT is intentionally out of scope for Phase 1).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.db.models.institutional.filer import F13Filer
    from app.db.models.institutional.holding import F13Holding


class F13Filing(Base):
    __tablename__ = "f13_filings"
    __table_args__ = (
        UniqueConstraint(
            "filer_id",
            "accession_number",
            name="uq_f13_filings_filer_accession",
        ),
        CheckConstraint(
            "form_type IN ('13F-HR', '13F-HR/A')",
            name="ck_f13_filings_form_type_valid",
        ),
        Index(
            "ix_f13_filings_filer_period_desc",
            "filer_id",
            text("report_period_end DESC"),
        ),
        Index(
            "ix_f13_filings_filer_filed_desc",
            "filer_id",
            text("filed_at DESC"),
        ),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    filer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("f13_filers.id", ondelete="CASCADE"),
        nullable=False,
    )
    accession_number: Mapped[str] = mapped_column(String(25), nullable=False)
    form_type: Mapped[str] = mapped_column(String(20), nullable=False)
    report_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # defaulted / nullable fields after
    total_value_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2),
        default=None,
    )
    options_notional_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2),
        default=None,
    )
    total_positions: Mapped[int | None] = mapped_column(Integer, default=None)
    raw_xml_url: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )

    filer: Mapped[F13Filer] = relationship(
        back_populates="filings",
        init=False,
    )
    holdings: Mapped[list[F13Holding]] = relationship(
        back_populates="filing",
        cascade="all, delete-orphan",
        init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<F13Filing id={self.id} filer_id={self.filer_id} "
            f"{self.form_type} period={self.report_period_end} "
            f"accession={self.accession_number}>"
        )
