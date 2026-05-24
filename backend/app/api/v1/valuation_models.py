from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.middleware.tier_guard import require_tier
from app.models.enums import UserTier
from app.models.price_estimate import PriceEstimate
from app.schemas.valuation import PriceEstimateBase, ValuationEstimatesResponse

router = APIRouter(
    prefix="/valuation",
    tags=["valuation"],
    dependencies=[Depends(require_tier(UserTier.PRO))],
)

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{symbol}/estimates", response_model=ValuationEstimatesResponse)
async def get_valuation_estimates(
    symbol: str,
    db: DbSession,
) -> ValuationEstimatesResponse:
    """Get all stored price estimates for a stock."""
    stock = await get_stock_or_404(db, symbol)

    # Fetch all estimates for this stock from the latest date available
    # 1. Find the latest date
    date_stmt = select(PriceEstimate.date).where(PriceEstimate.stock_id == stock.id).order_by(PriceEstimate.date.desc()).limit(1)
    date_res = await db.execute(date_stmt)
    latest_date = date_res.scalar_one_or_none()

    if not latest_date:
        return ValuationEstimatesResponse(symbol=symbol, estimates=[], latest_composite=None)

    # 2. Fetch all models for that date
    stmt = (
        select(PriceEstimate)
        .where(PriceEstimate.stock_id == stock.id)
        .where(PriceEstimate.date == latest_date)
    )
    result = await db.execute(stmt)
    estimates = result.scalars().all()

    composite = next((e for e in estimates if e.model_type == "composite"), None)
    others = [e for e in estimates if e.model_type != "composite"]

    return ValuationEstimatesResponse(
        symbol=symbol,
        estimates=[PriceEstimateBase.model_validate(e) for e in others],
        latest_composite=PriceEstimateBase.model_validate(composite) if composite else None
    )
