from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.financial_analysis.earnings_calendar import EarningsCalendarService
from app.modules.financial_analysis.finmind_tw_provider import FinMindTWFinancialProvider
from app.modules.financial_analysis.ratios import calculate_ratios
from app.modules.financial_analysis.scorer import calculate_health_score
from app.modules.financial_analysis.sec_edgar_provider import SECEdgarFinancialProvider
from app.modules.financial_analysis.tw_db_reader import read_tw_financials
from app.schemas.financial import (
    FinancialDataResponse,
    FinancialRatiosResponse,
    FinancialStatementResponse,
    FullAnalysisResponse,
    HealthScoreResponse,
)

router = APIRouter(prefix="/financials", tags=["financials"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_calendar_service = EarningsCalendarService()


def _is_tw_stock(symbol: str) -> bool:
    """Taiwan stock symbols are purely numeric (e.g., 2330, 0050)."""
    return symbol.isdigit()


async def _fetch_financial_data(symbol: str, db: AsyncSession):
    """
    Fetch financial data with DB-first strategy for TW stocks.

    TW stocks: read from financial_statements DB → fall back to FinMind live.
    US stocks: call SEC EDGAR (no DB storage yet).
    """
    if _is_tw_stock(symbol):
        data = await read_tw_financials(symbol, db)
        if data is not None:
            return data
        # DB miss — fall back to live FinMind fetch
        return await FinMindTWFinancialProvider().fetch_financials(symbol)
    else:
        return await SECEdgarFinancialProvider().fetch_financials(symbol)


def _build_full_response(data, symbol: str) -> FullAnalysisResponse:
    ratios_list = calculate_ratios(data)
    health_scores = [calculate_health_score(r) for r in ratios_list]

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
            symbol=r.symbol,
            period=r.period,
            gross_margin=r.gross_margin,
            operating_margin=r.operating_margin,
            net_margin=r.net_margin,
            roe=r.roe,
            roa=r.roa,
            inventory_turnover=r.inventory_turnover,
            receivable_turnover=r.receivable_turnover,
            current_ratio=r.current_ratio,
            quick_ratio=r.quick_ratio,
            debt_ratio=r.debt_ratio,
            revenue_growth=r.revenue_growth,
            net_income_growth=r.net_income_growth,
        )
        for r in ratios_list
    ]

    health_resp = [
        HealthScoreResponse(
            symbol=h.symbol,
            period=h.period,
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


# ------------------------------------------------------------------ #
# Endpoints                                                            #
# ------------------------------------------------------------------ #


@router.get("/{symbol}", response_model=FullAnalysisResponse)
async def get_full_analysis(symbol: str, db: DbSession) -> FullAnalysisResponse:
    """Get complete financial analysis: statements, ratios, health score.

    For Taiwan stocks (numeric symbols): reads from local DB first,
    falls back to live FinMind fetch on cache miss.
    For US stocks: calls SEC EDGAR live.
    """
    try:
        data = await _fetch_financial_data(symbol, db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch financials: {str(e)}")

    if not data.income_statements:
        raise HTTPException(status_code=404, detail=f"No financial data for '{symbol}'")

    return _build_full_response(data, symbol)


@router.get("/{symbol}/ratios", response_model=list[FinancialRatiosResponse])
async def get_ratios(symbol: str, db: DbSession) -> list[FinancialRatiosResponse]:
    """Get financial ratios only."""
    try:
        data = await _fetch_financial_data(symbol, db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch financials: {str(e)}")

    if not data.income_statements:
        raise HTTPException(status_code=404, detail=f"No financial data for '{symbol}'")

    ratios_list = calculate_ratios(data)
    return [
        FinancialRatiosResponse(
            symbol=r.symbol,
            period=r.period,
            gross_margin=r.gross_margin,
            operating_margin=r.operating_margin,
            net_margin=r.net_margin,
            roe=r.roe,
            roa=r.roa,
            inventory_turnover=r.inventory_turnover,
            receivable_turnover=r.receivable_turnover,
            current_ratio=r.current_ratio,
            quick_ratio=r.quick_ratio,
            debt_ratio=r.debt_ratio,
            revenue_growth=r.revenue_growth,
            net_income_growth=r.net_income_growth,
        )
        for r in ratios_list
    ]


@router.get("/{symbol}/calendar")
async def get_earnings_calendar(symbol: str, db: DbSession) -> list[dict]:
    """Return upcoming earnings filing events for a Taiwan stock.

    Shows the next 2 expected quarterly report deadlines and whether
    data is already available in our DB.
    """
    if not _is_tw_stock(symbol):
        raise HTTPException(
            status_code=400,
            detail="Earnings calendar is currently only supported for Taiwan stocks.",
        )

    events = await _calendar_service.get_calendar(symbol, db)
    latest = await _calendar_service.get_latest_filed_period(symbol, db)

    return [
        {
            "symbol": e.symbol,
            "period_label": e.period_label,
            "fiscal_year": e.fiscal_year,
            "fiscal_quarter": e.fiscal_quarter,
            "period_end_date": e.period_end_date.isoformat(),
            "deadline_date": e.deadline_date.isoformat(),
            "days_until_deadline": e.days_until_deadline,
            "already_in_db": e.already_in_db,
            "latest_available_period": latest,
        }
        for e in events
    ]
