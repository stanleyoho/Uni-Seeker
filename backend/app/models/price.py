from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_stock_prices_stock_id_date"),
        Index("ix_stock_prices_stock_id_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int] = mapped_column(BigInteger)
    change: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    change_percent: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
