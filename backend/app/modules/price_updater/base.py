from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StockPriceData:
    """Normalized price data returned by all providers."""
    symbol: str
    market: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal = Decimal("0")
    change_percent: Decimal = Decimal("0")
    name: str = ""


@runtime_checkable
class DataProvider(Protocol):
    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        """Fetch daily prices. If symbol is None, fetch all stocks."""
        ...

    @property
    def market(self) -> str:
        """Return the market identifier (e.g., 'TW_TWSE')."""
        ...
