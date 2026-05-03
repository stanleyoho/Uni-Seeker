from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BacktestResultRecord(Base):
    """Stores individual strategy backtest results linked to a job."""

    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("backtest_jobs.id", ondelete="CASCADE"),
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    strategy_name: Mapped[str] = mapped_column(String(200))
    strategy_params: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    equity_curve: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    trade_log: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    composite_mode: Mapped[str | None] = mapped_column(String(20), default=None)

    # Backtest metadata
    backtest_type: Mapped[str] = mapped_column(String(20), default="single")  # single, grid_search, auto_discovery, portfolio
    date_range_start: Mapped[date | None] = mapped_column(Date, default=None)
    date_range_end: Mapped[date | None] = mapped_column(Date, default=None)
    buy_hold_return: Mapped[float | None] = mapped_column(Float, default=None)
    trading_days: Mapped[int | None] = mapped_column(Integer, default=None)

    # Denormalized columns for efficient sorting / filtering
    total_return: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )
