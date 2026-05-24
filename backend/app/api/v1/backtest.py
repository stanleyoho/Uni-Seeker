import asyncio
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.config import settings
from app.middleware.tier_guard import require_tier
from app.models.enums import UserTier
from app.models.price import StockPrice
from app.modules.backtester.auto_discovery import AutoDiscoveryConfig, AutoDiscoveryEngine
from app.modules.backtester.engine import MIN_DATA_POINTS, BacktestConfig, BacktestEngine
from app.modules.finmind.client import FinMindClient
from app.modules.finmind.institutional_provider import FinMindInstitutionalProvider
from app.modules.strategy import create_default_registry
from app.modules.strategy.composite import CompositeStrategy
from app.schemas.backtest import (
    AutoDiscoveryRequest,
    BacktestRequest,
    BacktestResponse,
    CompositeBacktestRequest,
    MetricsResponse,
    TradeRecord,
)

router = APIRouter(
    prefix="/backtest",
    tags=["backtest"],
    dependencies=[Depends(require_tier(UserTier.PRO))],
)

_registry = create_default_registry()

_CHIP_STRATEGIES = {
    "institutional_follow", "margin_divergence", "foreign_trust_sync",
    "ownership_concentration", "margin_overleverage",
}


async def _fetch_chip_data(symbol: str, start_date: str, end_date: str) -> dict[str, list[dict]]:
    """Fetch institutional + margin + shareholding data from FinMind."""
    data_id = symbol.replace(".TW", "")
    client = FinMindClient(token=settings.finmind_api_token, base_url=settings.finmind_api_url)
    provider = FinMindInstitutionalProvider(client)

    inst = await provider.fetch_institutional(data_id, start_date, end_date)
    shld = await provider.fetch_shareholding(data_id, start_date, end_date)

    # Margin data from FinMind
    margin = await client.fetch(
        dataset="TaiwanStockMarginPurchaseShortSale",
        data_id=data_id, start_date=start_date, end_date=end_date,
    )

    return {"institutional": inst, "margin": margin, "shareholding": shld}


async def _fetch_prices(
    db: AsyncSession,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[StockPrice]:
    from datetime import date as _date
    stock = await get_stock_or_404(db, symbol)
    q = select(StockPrice).where(StockPrice.stock_id == stock.id)
    if start_date:
        q = q.where(StockPrice.date >= _date.fromisoformat(start_date))
    if end_date:
        q = q.where(StockPrice.date <= _date.fromisoformat(end_date))
    q = q.order_by(StockPrice.date.asc())
    result = await db.execute(q)
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

    prices = await _fetch_prices(db, req.symbol, req.start_date, req.end_date)

    config = BacktestConfig(
        initial_capital=req.initial_capital,
        fee_rate=req.fee_rate,
        tax_rate=req.tax_rate,
        position_size=req.position_size,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )
    engine = BacktestEngine(config=config)

    chip_data = None
    if req.strategy in _CHIP_STRATEGIES:
        start = str(prices[0].date)
        end = str(prices[-1].date)
        chip_data = await _fetch_chip_data(req.symbol, start, end)

    try:
        bt_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: engine.run(strategy, prices, symbol=req.symbol, chip_data=chip_data)
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
    prices = await _fetch_prices(db, req.symbol, req.start_date, req.end_date)

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


_AUTO_DISCOVERY_TIMEOUT = 120  # 2 minutes


@router.post("/run/auto-discovery")
async def run_auto_discovery(
    req: AutoDiscoveryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Run automatic strategy discovery for a stock.

    Tests all technical strategies, optimises parameters for the top performers,
    then evaluates composite combinations to find the best overall strategy.
    """
    prices = await _fetch_prices(db, req.symbol, req.start_date, req.end_date)

    config = AutoDiscoveryConfig(
        initial_capital=req.initial_capital,
        position_size=req.position_size,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )

    engine = AutoDiscoveryEngine(create_default_registry())

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: engine.run(config, prices, req.symbol),
            ),
            timeout=_AUTO_DISCOVERY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=f"Auto discovery timed out after {_AUTO_DISCOVERY_TIMEOUT} seconds",
        )

    return asdict(result)
