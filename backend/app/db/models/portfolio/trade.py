"""PortfolioTrade ORM — Portfolio Tracker Phase 1 / UNI-PORT-001.

One row per executed trade (BUY / SELL / DIVIDEND / SPLIT). Belongs to
exactly one `portfolio_accounts` row; cascade-deletes its lots on removal.
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
    from app.db.models.portfolio.lot import PortfolioLot


class PortfolioTrade(Base):
    __tablename__ = "portfolio_trades"
    __table_args__ = (
        Index(
            "ix_portfolio_trades_account_symbol",
            "account_id",
            "symbol",
            "market",
            "trade_date",
        ),
        # Defensive: positive price and qty when present. Allow NULL because
        # DIVIDEND / SPLIT rows may omit one or both per spec §6.2 Table 2.
        CheckConstraint(
            "(price IS NULL) OR (price > 0)",
            name="ck_portfolio_trades_price_positive",
        ),
        CheckConstraint(
            "(quantity IS NULL) OR (quantity > 0)",
            name="ck_portfolio_trades_qty_positive",
        ),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[Market] = mapped_column(MarketType, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    # defaulted / nullable fields after
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
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

    account: Mapped[PortfolioAccount] = relationship(back_populates="trades", init=False)
    lots: Mapped[list[PortfolioLot]] = relationship(
        back_populates="trade",
        cascade="all, delete-orphan",
        init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<PortfolioTrade id={self.id} account_id={self.account_id} "
            f"{self.action} {self.symbol} qty={self.quantity} @ {self.price}>"
        )
