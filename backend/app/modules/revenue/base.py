from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RevenueRecord:
    symbol: str
    period: str  # "2024-Q4" or "2024-12"
    period_type: str  # "quarterly" or "monthly"
    revenue: float
    currency: str = "TWD"


@runtime_checkable
class RevenueProvider(Protocol):
    async def fetch_revenue(self, symbol: str) -> list[RevenueRecord]: ...
