"""Portfolio backtest API endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.modules.backtester.portfolio_backtest import (
    PortfolioAllocation,
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
    RebalanceConfig,
)
from app.modules.strategy import create_default_registry
from app.schemas.portfolio import (
    PortfolioAllocationInput,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PortfolioMetricsResponse,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_registry = create_default_registry()


async def _fetch_prices_for_symbol(
    db: AsyncSession,
    symbol: str,
) -> list[StockPrice]:
    """Fetch price data for a single symbol, raising appropriate errors."""
    stock = await get_stock_or_404(db, symbol)
    query = (
        select(StockPrice).where(StockPrice.stock_id == stock.id).order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())
    if len(prices) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data for '{symbol}': need at least 20 data points, got {len(prices)}",
        )
    return prices


@router.post("/backtest", response_model=PortfolioBacktestResponse)
async def run_portfolio_backtest(
    req: PortfolioBacktestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PortfolioBacktestResponse:
    """Run a synchronous portfolio backtest across multiple stocks."""
    if not req.allocations:
        raise HTTPException(status_code=400, detail="At least one allocation is required")

    # Validate weights sum to 1.0
    total_weight = sum(a.weight for a in req.allocations)
    if abs(total_weight - 1.0) > 1e-4:
        raise HTTPException(
            status_code=400,
            detail=f"Allocation weights must sum to 1.0, got {total_weight:.6f}",
        )

    # Fetch prices for all symbols
    prices_map: dict[str, list[StockPrice]] = {}
    for alloc in req.allocations:
        prices_map[alloc.symbol] = await _fetch_prices_for_symbol(db, alloc.symbol)

    # Build PortfolioAllocation objects with strategy instances
    allocations: list[PortfolioAllocation] = []
    for alloc in req.allocations:
        try:
            strategy = _registry.get(
                alloc.strategy, **{k: v for k, v in alloc.params.items() if v is not None}
            )
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        allocations.append(
            PortfolioAllocation(
                symbol=alloc.symbol,
                weight=alloc.weight,
                strategy=strategy,
            )
        )

    # Build rebalance config
    rebalance = RebalanceConfig(mode=req.rebalance_mode)
    if req.rebalance_config:
        if "period_days" in req.rebalance_config:
            rebalance.period_days = int(req.rebalance_config["period_days"])
        if "threshold_pct" in req.rebalance_config:
            rebalance.threshold_pct = float(req.rebalance_config["threshold_pct"])

    config = PortfolioBacktestConfig(
        initial_capital=req.initial_capital,
        rebalance=rebalance,
    )

    engine = PortfolioBacktestEngine(config)
    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: engine.run(allocations, prices_map)
            ),
            timeout=30,
        )
    except TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail="Portfolio backtest timed out after 30 seconds",
        ) from e

    # Convert trade log to serializable dicts
    trade_log_dicts = [
        {
            "date": t.date,
            "symbol": t.symbol,
            "action": t.action,
            "price": t.price,
            "shares": t.shares,
            "reason": t.reason,
        }
        for t in result.trade_log
    ]

    pm = result.portfolio_metrics
    return PortfolioBacktestResponse(
        portfolio_metrics=PortfolioMetricsResponse(
            total_return=pm.get("total_return", 0.0),
            annualized_return=pm.get("annualized_return", 0.0),
            max_drawdown=pm.get("max_drawdown", 0.0),
            sharpe=pm.get("sharpe_ratio", 0.0),
        ),
        individual_metrics=result.individual_metrics,
        portfolio_equity_curve=result.portfolio_equity_curve,
        individual_equity_curves=result.individual_equity_curves,
        trade_log=trade_log_dicts,
        rebalance_log=result.rebalance_log,
        allocations=[
            PortfolioAllocationInput(
                symbol=a["symbol"],
                weight=a["weight"],
                strategy=a["strategy"],
            )
            for a in result.allocations
        ],
    )
