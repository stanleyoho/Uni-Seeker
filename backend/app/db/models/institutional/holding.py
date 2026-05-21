"""F13Holding ORM — 13F Holdings Tracker Phase 1 / UNI-F13-001.

One row per `<infoTable>` entry inside a 13F filing. Captures the raw
position as the filer reported it to the SEC, plus an optional
`stock_id` link to our `stocks` table when the CUSIP maps to a known
ticker. Unmapped CUSIPs are still ingested with `stock_id = NULL`.

`value_usd` is `value × 1000` — SEC reports value in thousands of
dollars but we persist the full-dollar number for arithmetic sanity.
`shares` only carries the qty when `sshPrnamtType=SH`; principal-
denominated holdings (`PRN`) leave it NULL and the raw qty lives in the
voting columns only — Phase 1 ignores non-share positions for display
but keeps them in the DB for completeness.

`put_call` CHECK refuses anything outside {'PUT', 'CALL', NULL}.
`stock_id → stocks.id ON DELETE SET NULL` — soft-unlinking a stock must
not destroy historical 13F records.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.db.models.institutional.filing import F13Filing


class F13Holding(Base):
    __tablename__ = "f13_holdings"
    __table_args__ = (
        CheckConstraint(
            "put_call IS NULL OR put_call IN ('PUT', 'CALL')",
            name="ck_f13_holdings_put_call_valid",
        ),
        Index("ix_f13_holdings_filing_id", "filing_id"),
        Index("ix_f13_holdings_cusip", "cusip"),
        Index(
            "ix_f13_holdings_stock_id",
            "stock_id",
            postgresql_where=text("stock_id IS NOT NULL"),
        ),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    filing_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("f13_filings.id", ondelete="CASCADE"),
        nullable=False,
    )
    cusip: Mapped[str] = mapped_column(String(9), nullable=False)
    name_of_issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    value_usd: Mapped[Decimal] = mapped_column(Numeric(24, 2), nullable=False)

    # defaulted / nullable fields after
    shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 0), default=None)
    put_call: Mapped[str | None] = mapped_column(String(10), default=None)
    investment_discretion: Mapped[str | None] = mapped_column(
        String(20), default=None,
    )
    voting_authority_sole: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 0), default=None,
    )
    voting_authority_shared: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 0), default=None,
    )
    voting_authority_none: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 0), default=None,
    )
    stock_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stocks.id", ondelete="SET NULL"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )

    filing: Mapped["F13Filing"] = relationship(
        back_populates="holdings", init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<F13Holding id={self.id} filing_id={self.filing_id} "
            f"{self.cusip} {self.name_of_issuer!r} "
            f"value={self.value_usd} put_call={self.put_call}>"
        )
