from typing import Any

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel


class ConditionSchema(StrictModel):
    indicator: str
    params: dict[str, Any] = {}
    op: str
    value: Any


class ScreenRequest(StrictModel):
    market: str | None = None
    conditions: list[ConditionSchema]
    operator: str = "AND"
    sort_by: str | None = None
    sort_order: str = "asc"
    limit: int = Field(default=50, le=500, ge=1)


class ScreenResultItem(BaseModel):
    symbol: str
    indicator_values: dict[str, float]


class ScreenResponse(BaseModel):
    results: list[ScreenResultItem]
    total: int


class IndustryScreenRequest(StrictModel):
    z_threshold: float = -1.0


class IndustryScreenResultItem(BaseModel):
    symbol: str
    name: str
    industry: str
    pe_ratio: float
    industry_avg_pe: float
    pe_z_score: float
    score: float


class IndustryScreenResponse(BaseModel):
    results: list[IndustryScreenResultItem]
    total: int
