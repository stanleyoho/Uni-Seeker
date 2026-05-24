from pydantic import BaseModel

from app.schemas.types import DecimalStr


class RevenueRecordResponse(BaseModel):
    period: str
    revenue: DecimalStr
    currency: str


class RevenueAnalysisResponse(BaseModel):
    symbol: str
    latest_revenue: DecimalStr
    qoq_growth: DecimalStr | None
    yoy_growth: DecimalStr | None
    is_revenue_high: bool
    is_revenue_low: bool
    trend: str
    consecutive_growth_quarters: int
    records: list[RevenueRecordResponse]
