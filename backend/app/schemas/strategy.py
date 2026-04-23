from pydantic import BaseModel


class StrategyInfo(BaseModel):
    name: str
    description: str
    params: dict[str, object]


class StrategyListResponse(BaseModel):
    strategies: list[StrategyInfo]
