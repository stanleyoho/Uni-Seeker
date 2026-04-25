from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarginTrading(Base):
    __tablename__ = "margin_trading"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "date", name="uq_margin_trading_stock_id_date"
        ),
        Index("ix_margin_trading_stock_id_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)
    margin_buy: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_sell: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_limit: Mapped[int] = mapped_column(BigInteger, default=0)
    short_buy: Mapped[int] = mapped_column(BigInteger, default=0)
    short_sell: Mapped[int] = mapped_column(BigInteger, default=0)
    short_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    short_limit: Mapped[int] = mapped_column(BigInteger, default=0)
    offset: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
