from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db, get_indicator_registry
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.screener.conditions import Condition, ConditionGroup
from app.modules.screener.engine import ScreenerEngine
from app.schemas.screener import (
    ScreenRequest,
    ScreenResponse,
    ScreenResultItem,
)

router = APIRouter(prefix="/screener", tags=["screener"])


async def _fetch_prices_grouped(
    db: AsyncSession,
    market_filter: str | None = None,
) -> dict[str, list[StockPrice]]:
    """Fetch all prices grouped by symbol string, with optional market filter."""
    query = (
        select(StockPrice, Stock.symbol.label("stock_symbol"))
        .join(Stock, Stock.id == StockPrice.stock_id)
        .order_by(Stock.symbol, StockPrice.date.asc())
    )
    if market_filter:
        query = query.where(Stock.market == market_filter)

    result = await db.execute(query)
    rows = result.all()

    stocks_prices: dict[str, list[StockPrice]] = {}
    for price, symbol in rows:
        stocks_prices.setdefault(symbol, []).append(price)

    return stocks_prices


@router.post("/screen", response_model=ScreenResponse)
async def screen_stocks(
    req: ScreenRequest,
    db: AsyncSession = Depends(get_db),
    registry: IndicatorRegistry = Depends(get_indicator_registry),
) -> ScreenResponse:
    # Build conditions
    conditions = ConditionGroup(
        operator=req.operator,
        rules=[
            Condition(indicator=c.indicator, params=c.params, op=c.op, value=c.value)
            for c in req.conditions
        ],
    )

    stocks_prices = await _fetch_prices_grouped(db, market_filter=req.market)

    # Run screener
    engine = ScreenerEngine(registry=registry)
    results = engine.screen(
        stocks_prices, conditions,
        sort_by=req.sort_by, sort_order=req.sort_order,
    )

    # Apply limit
    limited = results[:req.limit]

    return ScreenResponse(
        results=[ScreenResultItem(symbol=r.symbol, indicator_values=r.indicator_values) for r in limited],
        total=len(results),
    )


@router.get("/presets")
def list_presets() -> list[dict]:
    """List all available screener presets."""
    from app.modules.screener.presets import PRESETS

    return [
        {
            "key": p.key,
            "name_zh": p.name_zh,
            "name_en": p.name_en,
            "description_zh": p.description_zh,
            "description_en": p.description_en,
            "sort_by": p.sort_by,
        }
        for p in PRESETS.values()
    ]


@router.post("/presets/{preset_key}", response_model=ScreenResponse)
async def run_preset(
    preset_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    registry: IndicatorRegistry = Depends(get_indicator_registry),
    limit: int = Query(default=20, le=100),
) -> ScreenResponse:
    """Run a built-in screener preset."""
    from app.modules.screener.presets import PRESETS

    preset = PRESETS.get(preset_key)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_key}' not found")

    stocks_prices = await _fetch_prices_grouped(db)

    engine = ScreenerEngine(registry=registry)
    results = engine.screen(
        stocks_prices, preset.conditions,
        sort_by=preset.sort_by, sort_order=preset.sort_order,
    )
    limited = results[:limit]

    return ScreenResponse(
        results=[ScreenResultItem(symbol=r.symbol, indicator_values=r.indicator_values) for r in limited],
        total=len(results),
    )
