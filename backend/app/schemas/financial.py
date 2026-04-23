from typing import Any

from pydantic import BaseModel


class FinancialStatementResponse(BaseModel):
    period: str
    period_type: str
    data: dict[str, float]


class FinancialDataResponse(BaseModel):
    symbol: str
    currency: str
    income_statements: list[FinancialStatementResponse]
    balance_sheets: list[FinancialStatementResponse]
    cash_flows: list[FinancialStatementResponse]


class FinancialRatiosResponse(BaseModel):
    symbol: str
    period: str
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    inventory_turnover: float | None = None
    receivable_turnover: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_ratio: float | None = None
    revenue_growth: float | None = None
    net_income_growth: float | None = None


class HealthScoreResponse(BaseModel):
    symbol: str
    period: str
    total_score: float
    profitability_score: float
    efficiency_score: float
    leverage_score: float
    growth_score: float
    details: dict[str, str]


class FullAnalysisResponse(BaseModel):
    financials: FinancialDataResponse
    ratios: list[FinancialRatiosResponse]
    health_scores: list[HealthScoreResponse]
