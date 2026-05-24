from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry, get_stock_or_404
from app.cache import cache_delete_pattern, cache_get, cache_set, make_cache_key
from app.middleware.tier_guard import require_tier
from app.models.enums import UserTier
from app.models.price import StockPrice
from app.models.user import User
from app.modules.indicators.registry import IndicatorRegistry
from app.schemas.indicator import IndicatorListResponse, IndicatorRequest, IndicatorResponse

router = APIRouter(prefix="/indicators", tags=["indicators"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Registry = Annotated[IndicatorRegistry, Depends(get_indicator_registry)]
BasicUser = Annotated[User, Depends(require_tier(UserTier.BASIC))]

# Advanced indicators only available to Basic tier and above.
_ADVANCED_INDICATORS = {"MACD", "KD", "BB", "OBV"}


async def _compute_indicator(
    req: IndicatorRequest,
    db: AsyncSession,
    registry: IndicatorRegistry,
) -> IndicatorResponse:
    """Shared computation logic for indicator endpoints."""
    cache_key = make_cache_key("indicator", req.symbol, req.indicator, req.params)
    cached = await cache_get(cache_key)
    if cached is not None:
        return IndicatorResponse(**cached)

    try:
        indicator = registry.get(req.indicator)
    except KeyError as err:
        raise HTTPException(
            status_code=404, detail=f"Indicator '{req.indicator}' not found"
        ) from err

    stock = await get_stock_or_404(db, req.symbol)

    query = (
        select(StockPrice).where(StockPrice.stock_id == stock.id).order_by(StockPrice.date.asc())
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

    response = IndicatorResponse(
        symbol=req.symbol,
        indicator=req.indicator,
        values=indicator_result.values,
    )
    await cache_set(cache_key, response.model_dump(), ttl=1800)
    return response


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
    return await _compute_indicator(req, db, registry)


@router.post("/calculate/advanced", response_model=IndicatorResponse)
async def calculate_advanced_indicator(
    req: IndicatorRequest,
    db: DbSession,
    registry: Registry,
    user: BasicUser,
) -> IndicatorResponse:
    """進階指標（MACD/KD/BB/OBV）— Basic tier 以上可用。"""
    if req.indicator not in _ADVANCED_INDICATORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"{req.indicator} is not an advanced indicator; use /calculate instead."),
        )
    return await _compute_indicator(req, db, registry)


@router.post("/cache/clear")
async def clear_indicator_cache() -> dict[str, str]:
    """Clear all cached indicator results."""
    await cache_delete_pattern("indicator")
    return {"status": "indicator cache cleared"}
