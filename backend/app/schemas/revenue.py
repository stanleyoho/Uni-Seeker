from pydantic import BaseModel


class RevenueRecordResponse(BaseModel):
    period: str
    revenue: float
    currency: str


class RevenueAnalysisResponse(BaseModel):
    symbol: str
    latest_revenue: float
    qoq_growth: float | None
    yoy_growth: float | None
    is_revenue_high: bool
    is_revenue_low: bool
    trend: str
    consecutive_growth_quarters: int
    records: list[RevenueRecordResponse]
