import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.modules.backtester.engine import BacktestConfig, BacktestEngine, MIN_DATA_POINTS
from app.modules.strategy import create_default_registry
from app.modules.strategy.composite import CompositeStrategy
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    CompositeBacktestRequest,
    MetricsResponse,
    TradeRecord,
)

router = APIRouter(prefix="/backtest", tags=["backtest"])

_registry = create_default_registry()


async def _fetch_prices(db: AsyncSession, symbol: str) -> list[StockPrice]:
    stock = await get_stock_or_404(db, symbol)
    query = (
        select(StockPrice)
        .where(StockPrice.stock_id == stock.id)
        .order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())
    if len(prices) < MIN_DATA_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data for '{symbol}': need at least {MIN_DATA_POINTS} data points, got {len(prices)}",
        )
    return prices


def _build_response(symbol: str, strategy_name: str, bt_result: object) -> BacktestResponse:
    return BacktestResponse(
        symbol=symbol,
        strategy=strategy_name,
        metrics=MetricsResponse(
            total_return=bt_result.metrics.total_return,
            annualized_return=bt_result.metrics.annualized_return,
            max_drawdown=bt_result.metrics.max_drawdown,
            sharpe_ratio=bt_result.metrics.sharpe_ratio,
            win_rate=bt_result.metrics.win_rate,
            total_trades=bt_result.metrics.total_trades,
            profit_factor=bt_result.metrics.profit_factor,
        ),
        equity_curve=bt_result.equity_curve,
        trades=[
            TradeRecord(
                action=t["action"],
                date=t["date"],
                price=t["price"],
                shares=t["shares"],
                reason=t["reason"],
            )
            for t in bt_result.trade_log
        ],
    )


_BACKTEST_TIMEOUT_SECONDS = 30


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BacktestResponse:
    try:
        strategy = _registry.get(req.strategy, **{k: v for k, v in req.params.items() if v is not None})
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prices = await _fetch_prices(db, req.symbol)

    config = BacktestConfig(
        initial_capital=req.initial_capital,
        fee_rate=req.fee_rate,
        tax_rate=req.tax_rate,
        position_size=req.position_size,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )
    engine = BacktestEngine(config=config)

    try:
        bt_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: engine.run(strategy, prices, symbol=req.symbol)
            ),
            timeout=_BACKTEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=f"Backtest timed out after {_BACKTEST_TIMEOUT_SECONDS} seconds",
        )

    return _build_response(req.symbol, req.strategy, bt_result)


@router.post("/run/composite", response_model=BacktestResponse)
async def run_composite_backtest(
    req: CompositeBacktestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BacktestResponse:
    if len(req.strategies) < 2:
        raise HTTPException(status_code=400, detail="Composite strategy requires at least 2 sub-strategies")
    if req.mode not in ("all", "any", "majority"):
        raise HTTPException(status_code=400, detail=f"Invalid mode '{req.mode}'. Must be 'all', 'any', or 'majority'")

    sub_strategies = []
    for key in req.strategies:
        params = req.strategy_params.get(key, {})
        try:
            sub_strategies.append(_registry.get(key, **params))
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))

    composite = CompositeStrategy(strategies=sub_strategies, mode=req.mode)
    prices = await _fetch_prices(db, req.symbol)

    config = BacktestConfig(
        initial_capital=req.initial_capital,
        fee_rate=req.fee_rate,
        tax_rate=req.tax_rate,
        position_size=req.position_size,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )
    engine = BacktestEngine(config=config)

    try:
        bt_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: engine.run(composite, prices, symbol=req.symbol)
            ),
            timeout=_BACKTEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=f"Composite backtest timed out after {_BACKTEST_TIMEOUT_SECONDS} seconds",
        )

    strategy_name = f"composite({'+'.join(req.strategies)}, {req.mode})"
    return _build_response(req.symbol, strategy_name, bt_result)
