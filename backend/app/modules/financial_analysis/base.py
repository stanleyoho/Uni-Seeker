from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class FinancialStatement:
    """Represents one period (quarter/annual) of financial data."""
    period: str  # e.g. "2024Q4", "2024"
    period_type: str  # "quarterly" or "annual"
    data: dict[str, float]  # field_name -> value


@dataclass(frozen=True)
class FinancialData:
    """Complete financial data for a stock."""
    symbol: str
    currency: str
    income_statements: list[FinancialStatement] = field(default_factory=list)
    balance_sheets: list[FinancialStatement] = field(default_factory=list)
    cash_flows: list[FinancialStatement] = field(default_factory=list)


@runtime_checkable
class FinancialProvider(Protocol):
    async def fetch_financials(self, symbol: str) -> FinancialData: ...
