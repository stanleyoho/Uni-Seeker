from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IndustryMetrics(Base):
    """Aggregate financial metrics and valuations per industry per period."""

    __tablename__ = "industry_metrics"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    industry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("industries.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String(20), index=True)  # e.g., "2024-Q1"

    # Valuations (Medians)
    median_pe: Mapped[float | None] = mapped_column(Float, default=None)
    median_pb: Mapped[float | None] = mapped_column(Float, default=None)
    median_yield: Mapped[float | None] = mapped_column(Float, default=None)

    # Profitability (Medians)
    median_gross_margin: Mapped[float | None] = mapped_column(Float, default=None)
    median_operating_margin: Mapped[float | None] = mapped_column(Float, default=None)
    median_net_margin: Mapped[float | None] = mapped_column(Float, default=None)
    median_roe: Mapped[float | None] = mapped_column(Float, default=None)
    median_roa: Mapped[float | None] = mapped_column(Float, default=None)

    # Growth (Medians)
    median_revenue_growth_yoy: Mapped[float | None] = mapped_column(Float, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
