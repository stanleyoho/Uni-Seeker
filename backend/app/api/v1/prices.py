from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.schemas.price import StockPriceListResponse, StockPriceResponse

router = APIRouter(prefix="/prices", tags=["prices"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{symbol}", response_model=StockPriceListResponse)
async def get_stock_prices(
    symbol: str,
    db: DbSession,
    limit: int = Query(default=30, le=365),
    offset: int = Query(default=0, ge=0),
) -> StockPriceListResponse:
    query = (
        select(StockPrice)
        .where(StockPrice.symbol == symbol)
        .order_by(StockPrice.date.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    count_query = select(func.count()).select_from(StockPrice).where(StockPrice.symbol == symbol)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return StockPriceListResponse(
        data=[StockPriceResponse.model_validate(p) for p in prices],
        total=total,
    )
