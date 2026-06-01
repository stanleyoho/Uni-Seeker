from typing import Any

from pydantic import BaseModel

from app.schemas._base import StrictModel


class IndicatorRequest(StrictModel):
    symbol: str
    indicator: str
    params: dict[str, Any] = {}


class IndicatorResponse(BaseModel):
    symbol: str
    indicator: str
    values: dict[str, list[Any]]


class IndicatorListResponse(BaseModel):
    indicators: list[str]
