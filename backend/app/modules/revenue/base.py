from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RevenueRecord:
    symbol: str
    period: str  # "2024-Q4" or "2024-12"
    period_type: str  # "quarterly" or "monthly"
    revenue: float
    currency: str = "TWD"
    mom_growth: float | None = None  # month-over-month %
    yoy_growth: float | None = None  # year-over-year %
    industry: str = ""


@runtime_checkable
class RevenueProvider(Protocol):
    async def fetch_revenue(self, symbol: str) -> list[RevenueRecord]: ...
