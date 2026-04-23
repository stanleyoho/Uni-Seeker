from fastapi import APIRouter, HTTPException

from app.modules.revenue.yfinance_revenue import YFinanceRevenueProvider
from app.modules.revenue.analyzer import analyze_revenue
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
