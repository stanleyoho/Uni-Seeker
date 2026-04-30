"""Schemas for portfolio backtest endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioAllocationInput(BaseModel):
    symbol: str
    weight: float
    strategy: str
    params: dict[str, object] = {}


class PortfolioBacktestRequest(BaseModel):
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
    individual_metrics: dict[str, dict]
    portfolio_equity_curve: list[float]
    individual_equity_curves: dict[str, list[float]]
    trade_log: list[dict]
    rebalance_log: list[dict]
    allocations: list[PortfolioAllocationInput]
