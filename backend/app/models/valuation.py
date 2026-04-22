from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StockValuation(Base):
    __tablename__ = "stock_valuations"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_valuation_symbol_date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    pb_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    dividend_yield: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), default=None
    )
    industry: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
