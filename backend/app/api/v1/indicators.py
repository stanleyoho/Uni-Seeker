from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry
from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.schemas.indicator import IndicatorListResponse, IndicatorRequest, IndicatorResponse

router = APIRouter(prefix="/indicators", tags=["indicators"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Registry = Annotated[IndicatorRegistry, Depends(get_indicator_registry)]


@router.get("/", response_model=IndicatorListResponse)
def list_indicators(
    registry: Registry,
) -> IndicatorListResponse:
    return IndicatorListResponse(indicators=registry.list_names())


@router.post("/calculate", response_model=IndicatorResponse)
async def calculate_indicator(
    req: IndicatorRequest,
    db: DbSession,
    registry: Registry,
) -> IndicatorResponse:
    try:
        indicator = registry.get(req.indicator)
    except KeyError as err:
        raise HTTPException(
            status_code=404, detail=f"Indicator '{req.indicator}' not found"
        ) from err

    query = (
        select(StockPrice)
        .where(StockPrice.symbol == req.symbol)
        .order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for '{req.symbol}'")

    closes = [float(p.close) for p in prices]
    params = dict(req.params)
    if req.indicator == "KD":
        params["highs"] = [float(p.high) for p in prices]
        params["lows"] = [float(p.low) for p in prices]
    if req.indicator == "VOL":
        params["volumes"] = [p.volume for p in prices]

    indicator_result = indicator.calculate(closes, **params)

    return IndicatorResponse(
        symbol=req.symbol,
        indicator=req.indicator,
        values=indicator_result.values,
    )
