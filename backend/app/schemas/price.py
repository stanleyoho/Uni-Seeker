from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Market


class StockPriceResponse(BaseModel):
    symbol: str
    market: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal
    change_percent: Decimal


class StockPriceListResponse(BaseModel):
    data: list[StockPriceResponse]
    total: int


class PriceUpdateRequest(BaseModel):
    symbol: str | None = None
    market: Market | None = None


class PriceUpdateResponse(BaseModel):
    total_fetched: int
    duplicates_skipped: int
    invalid_skipped: int
    saved: int
    errors: list[str]


class BackfillRequest(BaseModel):
    symbols: list[str]  # e.g. ["2330.TW", "AAPL"]
    period: str = "1y"  # yfinance period: 1mo, 3mo, 6mo, 1y, 2y, 5y, max


class BackfillResponse(BaseModel):
    total_symbols: int
    total_prices_saved: int
    errors: list[str]
