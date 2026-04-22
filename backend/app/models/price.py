from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, BigInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import Market


class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_symbol_date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    market: Mapped[Market] = mapped_column()
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int] = mapped_column(BigInteger)
    change: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    change_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(), onupdate=func.now()
    )
