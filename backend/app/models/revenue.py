from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonthlyRevenue(Base):
    __tablename__ = "monthly_revenues"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    period: Mapped[str] = mapped_column(String(10), index=True)  # "2026-03"
    revenue: Mapped[float] = mapped_column(Float)
    mom_growth: Mapped[float | None] = mapped_column(Float, default=None)
    yoy_growth: Mapped[float | None] = mapped_column(Float, default=None)
    industry: Mapped[str] = mapped_column(String(50), default="")
    currency: Mapped[str] = mapped_column(String(10), default="TWD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
