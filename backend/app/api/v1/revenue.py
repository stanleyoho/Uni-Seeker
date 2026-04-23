from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.api.deps import get_db
from app.models.revenue import MonthlyRevenue
from app.modules.revenue.analyzer import analyze_revenue
from app.modules.revenue.twse_revenue import TWSERevenueProvider
from app.modules.revenue.yfinance_revenue import YFinanceRevenueProvider
from app.schemas.revenue import RevenueAnalysisResponse, RevenueRecordResponse

router = APIRouter(prefix="/revenue", tags=["revenue"])


@router.get("/{symbol}", response_model=RevenueAnalysisResponse)
async def get_revenue_analysis(symbol: str) -> RevenueAnalysisResponse:
    provider = YFinanceRevenueProvider()
    records = await provider.fetch_revenue(symbol)

    if not records:
        raise HTTPException(status_code=404, detail=f"No revenue data for '{symbol}'")

    analysis = analyze_revenue(records)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Cannot analyze revenue for '{symbol}'")

    return RevenueAnalysisResponse(
        symbol=analysis.symbol,
        latest_revenue=analysis.latest_revenue,
        qoq_growth=analysis.qoq_growth,
        yoy_growth=analysis.yoy_growth,
        is_revenue_high=analysis.is_revenue_high,
        is_revenue_low=analysis.is_revenue_low,
        trend=analysis.trend,
        consecutive_growth_quarters=analysis.consecutive_growth_quarters,
        records=[
            RevenueRecordResponse(period=r.period, revenue=r.revenue, currency=r.currency)
            for r in records
        ],
    )


@router.post("/update-tw")
async def update_tw_revenue(db: AsyncSession = Depends(get_db)) -> dict:
    """Fetch latest TWSE monthly revenue and store in database."""
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        provider = TWSERevenueProvider(client=client)
        records = await provider.fetch_all_revenue()

    stored = 0
    for rec in records:
        # Upsert: skip if already exists for this symbol+period
        existing = await db.execute(
            select(MonthlyRevenue).where(
                MonthlyRevenue.symbol == rec.symbol,
                MonthlyRevenue.period == rec.period,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        db.add(
            MonthlyRevenue(
                symbol=rec.symbol,
                period=rec.period,
                revenue=rec.revenue,
                mom_growth=rec.mom_growth,
                yoy_growth=rec.yoy_growth,
                industry=rec.industry,
                currency=rec.currency,
            )
        )
        stored += 1

    await db.commit()
    return {"fetched": len(records), "stored": stored}
