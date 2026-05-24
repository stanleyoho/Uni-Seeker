"""Financial metrics API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.financial_metrics import FinancialMetrics

router = APIRouter(prefix="/financial-metrics", tags=["financial-metrics"])


@router.get("/{symbol}")
async def get_metrics(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=8, ge=1, le=40),
):
    """Get financial metrics history for a stock."""
    stock = await get_stock_or_404(db, symbol)
    stmt = (
        select(FinancialMetrics)
        .where(FinancialMetrics.stock_id == stock.id)
        .order_by(
            FinancialMetrics.fiscal_year.desc(),
            FinancialMetrics.fiscal_quarter.desc(),
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = list(result.scalars().all())
    if not records:
        raise HTTPException(status_code=404, detail=f"No financial metrics for '{symbol}'")

    return [
        {
            "period": r.period,
            "fiscal_year": r.fiscal_year,
            "fiscal_quarter": r.fiscal_quarter,
            "gross_margin": r.gross_margin,
            "operating_margin": r.operating_margin,
            "net_margin": r.net_margin,
            "roe": r.roe,
            "roa": r.roa,
            "asset_turnover": r.asset_turnover,
            "debt_to_equity": r.debt_to_equity,
            "current_ratio": r.current_ratio,
            "quick_ratio": r.quick_ratio,
            "eps": r.eps,
            "revenue_growth_yoy": r.revenue_growth_yoy,
            "eps_growth_yoy": r.eps_growth_yoy,
            "operating_income_growth_yoy": r.operating_income_growth_yoy,
            "fcf": r.fcf,
            "operating_cf_ratio": r.operating_cf_ratio,
        }
        for r in records
    ]
