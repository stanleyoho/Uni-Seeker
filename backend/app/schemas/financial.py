from typing import Any

from pydantic import BaseModel

from app.schemas.types import DecimalStr


class FinancialStatementResponse(BaseModel):
    period: str
    period_type: str
    data: dict[str, DecimalStr]


class FinancialDataResponse(BaseModel):
    symbol: str
    currency: str
    income_statements: list[FinancialStatementResponse]
    balance_sheets: list[FinancialStatementResponse]
    cash_flows: list[FinancialStatementResponse]


class FinancialRatiosResponse(BaseModel):
    symbol: str
    period: str
    gross_margin: DecimalStr | None = None
    operating_margin: DecimalStr | None = None
    net_margin: DecimalStr | None = None
    roe: DecimalStr | None = None
    roa: DecimalStr | None = None
    inventory_turnover: DecimalStr | None = None
    receivable_turnover: DecimalStr | None = None
    current_ratio: DecimalStr | None = None
    quick_ratio: DecimalStr | None = None
    debt_ratio: DecimalStr | None = None
    revenue_growth: DecimalStr | None = None
    net_income_growth: DecimalStr | None = None


class HealthScoreResponse(BaseModel):
    symbol: str
    period: str
    total_score: DecimalStr
    profitability_score: DecimalStr
    efficiency_score: DecimalStr
    leverage_score: DecimalStr
    growth_score: DecimalStr
    details: dict[str, str]


class FullAnalysisResponse(BaseModel):
    financials: FinancialDataResponse
    ratios: list[FinancialRatiosResponse]
    health_scores: list[HealthScoreResponse]
