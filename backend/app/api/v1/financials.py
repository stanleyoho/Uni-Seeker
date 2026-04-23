from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.financial_analysis.yfinance_financials import YFinanceFinancialProvider
from app.modules.financial_analysis.ratios import calculate_ratios
from app.modules.financial_analysis.scorer import calculate_health_score
from app.schemas.financial import (
    FinancialDataResponse,
    FinancialRatiosResponse,
    FinancialStatementResponse,
    FullAnalysisResponse,
    HealthScoreResponse,
)

router = APIRouter(prefix="/financials", tags=["financials"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{symbol}", response_model=FullAnalysisResponse)
async def get_full_analysis(symbol: str) -> FullAnalysisResponse:
    """Get complete financial analysis: statements, ratios, health score."""
    provider = YFinanceFinancialProvider()

    try:
        data = await provider.fetch_financials(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch financials: {str(e)}")

    if not data.income_statements:
        raise HTTPException(status_code=404, detail=f"No financial data for '{symbol}'")

    # Calculate ratios and health scores
    ratios_list = calculate_ratios(data)
    health_scores = [calculate_health_score(r) for r in ratios_list]

    # Convert to response
    financials_resp = FinancialDataResponse(
        symbol=data.symbol,
        currency=data.currency,
        income_statements=[
            FinancialStatementResponse(period=s.period, period_type=s.period_type, data=s.data)
            for s in data.income_statements
        ],
        balance_sheets=[
            FinancialStatementResponse(period=s.period, period_type=s.period_type, data=s.data)
            for s in data.balance_sheets
        ],
        cash_flows=[
            FinancialStatementResponse(period=s.period, period_type=s.period_type, data=s.data)
            for s in data.cash_flows
        ],
    )

    ratios_resp = [
        FinancialRatiosResponse(
            symbol=r.symbol, period=r.period,
            gross_margin=r.gross_margin, operating_margin=r.operating_margin,
            net_margin=r.net_margin, roe=r.roe, roa=r.roa,
            inventory_turnover=r.inventory_turnover,
            receivable_turnover=r.receivable_turnover,
            current_ratio=r.current_ratio, quick_ratio=r.quick_ratio,
            debt_ratio=r.debt_ratio,
            revenue_growth=r.revenue_growth, net_income_growth=r.net_income_growth,
        )
        for r in ratios_list
    ]

    health_resp = [
        HealthScoreResponse(
            symbol=h.symbol, period=h.period,
            total_score=h.total_score,
            profitability_score=h.profitability_score,
            efficiency_score=h.efficiency_score,
            leverage_score=h.leverage_score,
            growth_score=h.growth_score,
            details=h.details,
        )
        for h in health_scores
    ]

    return FullAnalysisResponse(
        financials=financials_resp,
        ratios=ratios_resp,
        health_scores=health_resp,
    )


@router.get("/{symbol}/ratios", response_model=list[FinancialRatiosResponse])
async def get_ratios(symbol: str) -> list[FinancialRatiosResponse]:
    """Get financial ratios only."""
    provider = YFinanceFinancialProvider()

    try:
        data = await provider.fetch_financials(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch financials: {str(e)}")

    if not data.income_statements:
        raise HTTPException(status_code=404, detail=f"No financial data for '{symbol}'")

    ratios_list = calculate_ratios(data)
    return [
        FinancialRatiosResponse(
            symbol=r.symbol, period=r.period,
            gross_margin=r.gross_margin, operating_margin=r.operating_margin,
            net_margin=r.net_margin, roe=r.roe, roa=r.roa,
            inventory_turnover=r.inventory_turnover,
            receivable_turnover=r.receivable_turnover,
            current_ratio=r.current_ratio, quick_ratio=r.quick_ratio,
            debt_ratio=r.debt_ratio,
            revenue_growth=r.revenue_growth, net_income_growth=r.net_income_growth,
        )
        for r in ratios_list
    ]
