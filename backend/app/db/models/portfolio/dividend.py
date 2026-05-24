"""PortfolioDividend ORM — Portfolio Tracker Phase 2 / UNI-PORT-002.

One row per dividend event (cash or stock) credited to a portfolio
account. Belongs to exactly one `portfolio_accounts` row; cascade-
deleted when the parent account is removed.

Notes
-----
- `dividend_type` is a String(10) with CHECK constraint (not a PG ENUM)
  to keep the enum-type namespace small and avoid an Alembic migration
  for every new dividend variant.
- `total_amount` / `net_amount` are NOT stored — derived in the service
  layer from `amount_per_share × quantity_at_record − withholding_tax`.
  Keeps SQLite test parity with Postgres prod.
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
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Market, MarketType

if TYPE_CHECKING:
    from app.db.models.portfolio.account import PortfolioAccount


class PortfolioDividend(Base):
    __tablename__ = "portfolio_dividends"
    __table_args__ = (
        Index(
            "ix_portfolio_dividends_account_ex_date",
            "account_id",
            "ex_dividend_date",
        ),
        CheckConstraint(
            "dividend_type IN ('CASH', 'STOCK')",
            name="ck_portfolio_dividends_type_valid",
        ),
        CheckConstraint(
            "amount_per_share > 0",
            name="ck_portfolio_dividends_amount_positive",
        ),
        CheckConstraint(
            "quantity_at_record > 0",
            name="ck_portfolio_dividends_qty_positive",
        ),
        CheckConstraint(
            "withholding_tax >= 0",
            name="ck_portfolio_dividends_withholding_nonneg",
        ),
    )

    # non-default fields first (MappedAsDataclass convention)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[Market] = mapped_column(MarketType, nullable=False)
    dividend_type: Mapped[str] = mapped_column(String(10), nullable=False)
    ex_dividend_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_per_share: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quantity_at_record: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    # defaulted / nullable fields after
    pay_date: Mapped[date | None] = mapped_column(Date, default=None)
    currency: Mapped[str] = mapped_column(String(3), default="TWD", nullable=False)
    withholding_tax: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), default=Decimal("0"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account: Mapped[PortfolioAccount] = relationship(back_populates="dividends", init=False)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<PortfolioDividend id={self.id} account_id={self.account_id} "
            f"{self.dividend_type} {self.symbol} "
            f"{self.amount_per_share}×{self.quantity_at_record} "
            f"ex={self.ex_dividend_date}>"
        )
