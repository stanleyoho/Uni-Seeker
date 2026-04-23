from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.modules.backtester.engine import BacktestConfig, BacktestEngine
from app.modules.strategy.builtin import MACrossoverStrategy, RSIOversoldStrategy
from app.schemas.backtest import BacktestRequest, BacktestResponse, MetricsResponse, TradeRecord

router = APIRouter(prefix="/backtest", tags=["backtest"])

STRATEGY_MAP = {
    "ma_crossover": MACrossoverStrategy,
    "rsi_oversold": RSIOversoldStrategy,
}


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BacktestResponse:
    # Get strategy
    strategy_cls = STRATEGY_MAP.get(req.strategy)
    if not strategy_cls:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {req.strategy}. Available: {list(STRATEGY_MAP.keys())}",
        )

    strategy = strategy_cls(**{k: v for k, v in req.params.items() if v is not None})

    # Fetch prices
    query = (
        select(StockPrice)
        .where(StockPrice.symbol == req.symbol)
        .order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    if len(prices) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data for '{req.symbol}': need at least 20 data points, got {len(prices)}",
        )

    # Run backtest
    config = BacktestConfig(
        initial_capital=req.initial_capital,
        fee_rate=req.fee_rate,
        tax_rate=req.tax_rate,
        position_size=req.position_size,
    )
    engine = BacktestEngine(config=config)
    bt_result = engine.run(strategy, prices, symbol=req.symbol)

    return BacktestResponse(
        symbol=req.symbol,
        strategy=req.strategy,
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
