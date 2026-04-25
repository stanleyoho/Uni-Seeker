"""Market heatmap API: sector-aggregated performance data."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/heatmap", tags=["heatmap"])


class HeatmapStock(BaseModel):
    symbol: str
    name: str
    close: float
    change_percent: float
    volume: int


class HeatmapSector(BaseModel):
    industry: str
    stock_count: int
    avg_change_percent: float
    total_volume: int
    stocks: list[HeatmapStock]


class HeatmapResponse(BaseModel):
    sectors: list[HeatmapSector]
    date: str | None


@router.get("/sectors")
async def get_heatmap_data(
    db: DbSession,
    market_filter: str | None = Query(None),
    top_n: int = Query(default=5, description="Top N stocks per sector"),
) -> HeatmapResponse:
    """Sector heatmap data: avg change per sector with top movers."""

    # Find latest date
    latest_q = select(func.max(StockPrice.date))
    if market_filter:
        latest_q = latest_q.join(Stock, Stock.id == StockPrice.stock_id).where(
            Stock.market == market_filter
        )
    latest_result = await db.execute(latest_q)
    latest_date = latest_result.scalar()

    if not latest_date:
        return HeatmapResponse(sectors=[], date=None)

    # Get all stocks with prices for latest date, grouped by industry
    q = (
        select(
            Industry.name.label("industry_name"),
            Stock.symbol,
            Stock.name,
            StockPrice.close,
            StockPrice.change_percent,
            StockPrice.volume,
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .join(Industry, Industry.id == Stock.industry_id, isouter=True)
        .where(StockPrice.date == latest_date)
        .where(Stock.industry_id.isnot(None))
        .where(StockPrice.change_percent.isnot(None))
    )
    if market_filter:
        q = q.where(Stock.market == market_filter)

    result = await db.execute(q)
    rows = result.all()

    # Group by industry
    sector_map: dict[str, list] = {}
    for row in rows:
        industry = row.industry_name or "Other"
        if industry not in sector_map:
            sector_map[industry] = []
        sector_map[industry].append(
            HeatmapStock(
                symbol=row.symbol,
                name=row.name or row.symbol,
                close=float(row.close or 0),
                change_percent=float(row.change_percent or 0),
                volume=int(row.volume or 0),
            )
        )

    # Build sector response
    sectors: list[HeatmapSector] = []
    for industry, stocks in sector_map.items():
        avg_change = sum(s.change_percent for s in stocks) / len(stocks) if stocks else 0
        total_vol = sum(s.volume for s in stocks)
        # Sort stocks by absolute change_percent desc, take top N
        sorted_stocks = sorted(stocks, key=lambda s: abs(s.change_percent), reverse=True)[:top_n]

        sectors.append(
            HeatmapSector(
                industry=industry,
                stock_count=len(stocks),
                avg_change_percent=round(avg_change, 2),
                total_volume=total_vol,
                stocks=sorted_stocks,
            )
        )

    # Sort sectors by stock_count desc (largest sectors first)
    sectors.sort(key=lambda s: s.stock_count, reverse=True)

    return HeatmapResponse(sectors=sectors, date=str(latest_date))
