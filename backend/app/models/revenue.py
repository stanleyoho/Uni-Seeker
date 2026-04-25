from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonthlyRevenue(Base):
    __tablename__ = "monthly_revenues"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "period", name="uq_monthly_revenues_stock_id_period"
        ),
        Index("ix_monthly_revenues_stock_id_period", "stock_id", "period"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    period: Mapped[str] = mapped_column(String(10))  # "2026-03"
    revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    mom_growth: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    yoy_growth: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    currency: Mapped[str] = mapped_column(String(10), default="TWD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
