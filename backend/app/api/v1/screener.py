from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry
from app.models.enums import Market
from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.screener.conditions import Condition, ConditionGroup
from app.modules.screener.engine import ScreenerEngine
from app.schemas.screener import (
    ScreenRequest,
    ScreenResponse,
    ScreenResultItem,
)

router = APIRouter(prefix="/screener", tags=["screener"])


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

    # Fetch all prices grouped by symbol
    query = select(StockPrice).order_by(StockPrice.symbol, StockPrice.date.asc())
    if req.market:
        market_prefix = req.market + "_"
        query = query.where(StockPrice.market.in_([
            m for m in Market if m.value.startswith(market_prefix)
        ]))

    result = await db.execute(query)
    all_prices = list(result.scalars().all())

    # Group by symbol
    stocks_prices: dict[str, list[StockPrice]] = {}
    for price in all_prices:
        stocks_prices.setdefault(price.symbol, []).append(price)

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
