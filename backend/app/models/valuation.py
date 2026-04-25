from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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


class StockValuation(Base):
    __tablename__ = "stock_valuations"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "date", name="uq_stock_valuations_stock_id_date"
        ),
        Index("ix_stock_valuations_stock_id_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    pb_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    dividend_yield: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), default=None
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
