"""PortfolioAccount ORM — Portfolio Tracker Phase 1 / UNI-PORT-001.

A user's brokerage account holding a set of trades. One user may own
many accounts. Cascade deletes everything below it when removed.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Market, MarketType

if TYPE_CHECKING:
    from app.db.models.portfolio.dividend import PortfolioDividend
    from app.db.models.portfolio.lot import PortfolioLot
    from app.db.models.portfolio.position import PortfolioPosition
    from app.db.models.portfolio.trade import PortfolioTrade


class PortfolioAccount(Base):
    __tablename__ = "portfolio_accounts"
    __table_args__ = (Index("ix_portfolio_accounts_user_id", "user_id"),)

    # non-default fields first (MappedAsDataclass)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[Market] = mapped_column(MarketType, nullable=False)

    # defaulted / nullable fields after
    currency: Mapped[str] = mapped_column(String(10), default="TWD", nullable=False)
    broker: Mapped[str | None] = mapped_column(String(50), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )

    # relationships (init=False — populated by ORM, not constructor)
    trades: Mapped[list[PortfolioTrade]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        init=False,
    )
    lots: Mapped[list[PortfolioLot]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        init=False,
    )
    positions: Mapped[list[PortfolioPosition]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        init=False,
    )
    dividends: Mapped[list[PortfolioDividend]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        init=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<PortfolioAccount id={self.id} user_id={self.user_id} "
            f"name={self.name!r} market={self.market}>"
        )
