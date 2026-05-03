from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Market
from app.schemas.types import DecimalStr


class StockPriceResponse(BaseModel):
    symbol: str
    market: str
    date: date
    open: DecimalStr
    high: DecimalStr
    low: DecimalStr
    close: DecimalStr
    volume: int
    change: DecimalStr
    change_percent: DecimalStr


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
