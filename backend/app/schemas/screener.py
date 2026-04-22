from typing import Any

from pydantic import BaseModel


class ConditionSchema(BaseModel):
    indicator: str
    params: dict[str, Any] = {}
    op: str
    value: Any


class ScreenRequest(BaseModel):
    market: str | None = None
    conditions: list[ConditionSchema]
    operator: str = "AND"
    sort_by: str | None = None
    sort_order: str = "asc"
    limit: int = 50


class ScreenResultItem(BaseModel):
    symbol: str
    indicator_values: dict[str, float]


class ScreenResponse(BaseModel):
    results: list[ScreenResultItem]
    total: int


class IndustryScreenRequest(BaseModel):
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
