from pydantic import BaseModel


class MarginDataResponse(BaseModel):
    symbol: str
    name: str
    margin_buy: int
    margin_sell: int
    margin_balance: int
    margin_limit: int
    margin_usage_pct: float  # margin_balance / margin_limit * 100
    short_buy: int
    short_sell: int
    short_balance: int
    short_limit: int
    short_usage_pct: float
    offset: int
    margin_short_ratio: float  # 券資比 = short_balance / margin_balance


class MarginListResponse(BaseModel):
    data: list[MarginDataResponse]
    total: int


class MarginUpdateResponse(BaseModel):
    fetched: int
    saved: int
