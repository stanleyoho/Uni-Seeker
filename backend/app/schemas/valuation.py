from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.types import DecimalStr


class PriceEstimateBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    model_type: str
    date: date
    cheap_price: DecimalStr | None = None
    fair_price: DecimalStr | None = None
    expensive_price: DecimalStr | None = None
    confidence: DecimalStr
    details: dict[str, Any] = {}


class PriceEstimateResponse(PriceEstimateBase):
    model_config = ConfigDict(from_attributes=True)
    symbol: str


class ValuationEstimatesResponse(BaseModel):
    symbol: str
    estimates: list[PriceEstimateBase]
    latest_composite: PriceEstimateBase | None = None
