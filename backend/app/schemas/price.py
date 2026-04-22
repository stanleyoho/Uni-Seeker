from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Market


class StockPriceResponse(BaseModel):
    symbol: str
    market: Market
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal
    change_percent: Decimal

    model_config = {"from_attributes": True}


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
