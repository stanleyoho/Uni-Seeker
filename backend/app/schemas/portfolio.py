"""Schemas for portfolio backtest endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas._base import StrictModel


class PortfolioAllocationInput(StrictModel):
    symbol: str
    weight: float
    strategy: str
    params: dict[str, object] = {}


class PortfolioBacktestRequest(StrictModel):
    allocations: list[PortfolioAllocationInput]
    rebalance_mode: str = "none"
    rebalance_config: dict[str, object] = {}
    initial_capital: float = 1_000_000


class PortfolioMetricsResponse(BaseModel):
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe: float


class PortfolioBacktestResponse(BaseModel):
    portfolio_metrics: PortfolioMetricsResponse
    individual_metrics: dict[str, dict[str, Any]]
    portfolio_equity_curve: list[float]
    individual_equity_curves: dict[str, list[float]]
    trade_log: list[dict[str, Any]]
    rebalance_log: list[dict[str, Any]]
    allocations: list[PortfolioAllocationInput]
