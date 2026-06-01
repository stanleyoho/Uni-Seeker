"""Portfolio backtest API endpoints."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.models.stock import Stock
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
    """Fetch price data for a single symbol, raising appropriate errors.

    Single-symbol path — kept around for completeness even though the
    backtest endpoint now uses :func:`_fetch_prices_for_symbols` (plural)
    to avoid N+1.
    """
    stock = await get_stock_or_404(db, symbol)
    query = (
        select(StockPrice).where(StockPrice.stock_id == stock.id).order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())
    if len(prices) < 20:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient data for '{symbol}': need at least 20 data points, got {len(prices)}"
            ),
        )
    return prices


async def _fetch_prices_for_symbols(
    db: AsyncSession,
    symbols: list[str],
) -> dict[str, list[StockPrice]]:
    """Batched price fetch for portfolio backtests — TWO queries total
    regardless of allocation count.

    Before (audit-flagged): ``run_portfolio_backtest`` called the
    single-symbol helper inside a ``for alloc in req.allocations`` loop
    → 2 queries per allocation (stock lookup + price fetch) → 2N
    round-trips for an N-stock portfolio.

    After: one ``WHERE symbol IN (...)`` over ``stocks`` + one
    ``WHERE stock_id IN (...)`` over ``stock_prices``, grouped on the
    Python side via the (stock_id → symbol) map. Same downstream
    behaviour (404 on unknown symbol, 400 on <20 data points) so
    callers don't need to change.
    """
    if not symbols:
        return {}

    # Pull the stocks first so we can surface a precise 404 before doing
    # the (larger) price fetch.
    stock_rows = (await db.execute(select(Stock).where(Stock.symbol.in_(symbols)))).scalars().all()
    found: dict[str, Stock] = {s.symbol: s for s in stock_rows}
    missing = [s for s in symbols if s not in found]
    if missing:
        # Mirror the single-symbol helper's 404 surface — fail on the first
        # missing symbol so the client gets the same error shape they'd see
        # if they'd asked for that one symbol on its own.
        raise HTTPException(status_code=404, detail=f"Stock '{missing[0]}' not found")

    id_to_symbol = {s.id: s.symbol for s in stock_rows}
    prices_by_symbol: dict[str, list[StockPrice]] = {s: [] for s in symbols}

    rows = await db.execute(
        select(StockPrice)
        .where(StockPrice.stock_id.in_(list(id_to_symbol.keys())))
        .order_by(StockPrice.stock_id, StockPrice.date.asc())
    )
    for price in rows.scalars().all():
        sym = id_to_symbol.get(price.stock_id)
        if sym is not None:
            prices_by_symbol[sym].append(price)

    # Same 20-data-point gate the single-symbol path enforces. Done after
    # the batched fetch so we still raise a deterministic 400 even when
    # several symbols are short on history.
    for sym, prices in prices_by_symbol.items():
        if len(prices) < 20:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient data for '{sym}': need at least 20 data points, "
                    f"got {len(prices)}"
                ),
            )
    return prices_by_symbol


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

    # Fetch prices for all symbols in TWO queries (was 2N before — see
    # `_fetch_prices_for_symbols` docstring). Preserves uniqueness via
    # set() so callers passing the same symbol twice don't double-fetch.
    prices_map = await _fetch_prices_for_symbols(
        db,
        list({a.symbol for a in req.allocations}),
    )

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
            rebalance.period_days = int(req.rebalance_config["period_days"])  # type: ignore[call-overload]
        if "threshold_pct" in req.rebalance_config:
            rebalance.threshold_pct = float(req.rebalance_config["threshold_pct"])  # type: ignore[arg-type]

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
