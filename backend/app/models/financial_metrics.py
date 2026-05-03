from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FinancialMetrics(Base):
    """Pre-computed financial ratios and metrics per stock per quarter."""

    __tablename__ = "financial_metrics"
    __table_args__ = (
        UniqueConstraint("stock_id", "period", name="uq_fin_metrics_stock_period"),
        Index("ix_fin_metrics_stock_period", "stock_id", "period"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE")
    )
    period: Mapped[str] = mapped_column(String(10))  # "2024-Q1"
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    fiscal_quarter: Mapped[int] = mapped_column(SmallInteger)

    # Profitability
    gross_margin: Mapped[float | None] = mapped_column(Float, default=None)
    operating_margin: Mapped[float | None] = mapped_column(Float, default=None)
    net_margin: Mapped[float | None] = mapped_column(Float, default=None)
    roe: Mapped[float | None] = mapped_column(Float, default=None)
    roa: Mapped[float | None] = mapped_column(Float, default=None)

    # Efficiency
    asset_turnover: Mapped[float | None] = mapped_column(Float, default=None)

    # Leverage
    debt_to_equity: Mapped[float | None] = mapped_column(Float, default=None)
    current_ratio: Mapped[float | None] = mapped_column(Float, default=None)
    quick_ratio: Mapped[float | None] = mapped_column(Float, default=None)

    # Per-share
    eps: Mapped[float | None] = mapped_column(Float, default=None)

    # Growth (YoY)
    revenue_growth_yoy: Mapped[float | None] = mapped_column(Float, default=None)
    eps_growth_yoy: Mapped[float | None] = mapped_column(Float, default=None)
    operating_income_growth_yoy: Mapped[float | None] = mapped_column(
        Float, default=None
    )

    # Cash flow
    fcf: Mapped[float | None] = mapped_column(Float, default=None)
    operating_cf_ratio: Mapped[float | None] = mapped_column(Float, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
