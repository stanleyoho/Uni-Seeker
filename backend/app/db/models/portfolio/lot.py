"""PortfolioLot ORM — Portfolio Tracker Phase 1 / UNI-PORT-001.

FIFO lot. Created when a BUY trade is recorded; `remaining_qty` is
decremented as SELL trades consume oldest-open lots first. Exhaustion
flag is the cheap predicate the FIFO engine filters on.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Market, MarketType

if TYPE_CHECKING:
    from app.db.models.portfolio.account import PortfolioAccount
    from app.db.models.portfolio.trade import PortfolioTrade


class PortfolioLot(Base):
    __tablename__ = "portfolio_lots"
    __table_args__ = (
        Index(
            "ix_portfolio_lots_fifo",
            "account_id",
            "symbol",
            "market",
            "is_exhausted",
            "trade_id",
        ),
        CheckConstraint("original_qty > 0", name="ck_portfolio_lots_original_qty_positive"),
        CheckConstraint("remaining_qty >= 0", name="ck_portfolio_lots_remaining_qty_nonneg"),
        CheckConstraint("cost_per_unit > 0", name="ck_portfolio_lots_cost_positive"),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    trade_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_trades.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[Market] = mapped_column(MarketType, nullable=False)
    original_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    # defaulted fields after
    is_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    account: Mapped[PortfolioAccount] = relationship(back_populates="lots", init=False)
    trade: Mapped[PortfolioTrade] = relationship(back_populates="lots", init=False)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<PortfolioLot id={self.id} trade_id={self.trade_id} "
            f"{self.symbol} remaining={self.remaining_qty}/{self.original_qty} "
            f"exhausted={self.is_exhausted}>"
        )
