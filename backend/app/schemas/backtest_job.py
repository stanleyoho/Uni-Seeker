"""Schemas for backtest job queue and history endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas._base import StrictModel


class JobEnqueueRequest(StrictModel):
    symbol: str
    job_type: str = "single"  # single, composite, grid_search
    strategy: str | None = None
    strategies: list[str] | None = None
    mode: str = "majority"
    params: dict[str, object] = {}
    strategy_params: dict[str, dict[str, object]] = {}
    param_grid: dict[str, list[Any]] | None = None
    initial_capital: float = 1_000_000
    position_size: float = 0.95
    stop_loss: float | None = None
    take_profit: float | None = None


class JobStatusResponse(BaseModel):
    id: int
    symbol: str
    job_type: str
    status: str
    progress_pct: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class QueueStatusResponse(BaseModel):
    jobs: list[JobStatusResponse]
    running_count: int
    pending_count: int


class TradeLogEntry(BaseModel):
    date: str
    action: str
    price: float
    shares: int
    reason: str


class BacktestHistoryItem(BaseModel):
    id: int
    job_id: int
    symbol: str
    strategy_name: str
    strategy_params: dict[str, Any]
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profit_factor: float
    trade_log: list[TradeLogEntry] | None = None
    equity_curve: list[float] | None = None
    backtest_type: str = "single"
    composite_mode: str | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    buy_hold_return: float | None = None
    trading_days: int | None = None
    created_at: str


class BacktestHistoryResponse(BaseModel):
    results: list[BacktestHistoryItem]
    total: int


class JobResultResponse(BaseModel):
    job: JobStatusResponse
    results: list[BacktestHistoryItem]
