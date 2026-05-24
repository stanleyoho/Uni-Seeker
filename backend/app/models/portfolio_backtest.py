from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PortfolioBacktestRecord(Base):
    """Stores portfolio-level backtest results with allocation details."""

    __tablename__ = "portfolio_backtests"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("backtest_jobs.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    rebalance_mode: Mapped[str] = mapped_column(String(20))
    allocations: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    rebalance_config: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    equity_curve: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    individual_curves: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )
