"""PortfolioPosition ORM — Portfolio Tracker Phase 1 / UNI-PORT-001.

Materialized roll-up of open lots for a (account, symbol, market) tuple.
One row per holding; updated atomically by the trade-processing service
on every trade upsert. Uniqueness is the upsert key.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Market, MarketType

if TYPE_CHECKING:
    from app.db.models.portfolio.account import PortfolioAccount


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "symbol", "market",
            name="uq_portfolio_positions_account_symbol_market",
        ),
        CheckConstraint(
            "quantity >= 0", name="ck_portfolio_positions_qty_nonneg"
        ),
    )

    # non-default fields first
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[Market] = mapped_column(MarketType, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    # defaulted / nullable fields after
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), default=Decimal("0")
    )
    avg_cost_fifo: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 8), default=None
    )
    total_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 8), default=None
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), default=Decimal("0")
    )
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    account: Mapped["PortfolioAccount"] = relationship(
        back_populates="positions", init=False
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<PortfolioPosition id={self.id} account_id={self.account_id} "
            f"{self.symbol} qty={self.quantity} closed={self.is_closed}>"
        )
