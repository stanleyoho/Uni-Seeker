from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.stock import Stock
from pydantic import BaseModel

router = APIRouter(prefix="/stocks", tags=["stocks"])


class StockSearchResult(BaseModel):
    symbol: str
    name: str
    market: str

    model_config = {"from_attributes": True}


class StockSearchResponse(BaseModel):
    results: list[StockSearchResult]


@router.get("/search", response_model=StockSearchResponse)
async def search_stocks(
    q: Annotated[str, Query(min_length=1, max_length=20)],
    limit: int = Query(default=10, le=50),
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
) -> StockSearchResponse:
    """Search stocks by symbol or name prefix."""
    pattern = f"%{q}%"
    query = (
        select(Stock)
        .where(
            or_(
                Stock.symbol.ilike(pattern),
                Stock.name.ilike(pattern),
            )
        )
        .where(Stock.is_active.is_(True))
        .order_by(Stock.symbol)
        .limit(limit)
    )
    result = await db.execute(query)
    stocks = list(result.scalars().all())

    return StockSearchResponse(
        results=[
            StockSearchResult(symbol=s.symbol, name=s.name, market=s.market.value)
            for s in stocks
        ]
    )
