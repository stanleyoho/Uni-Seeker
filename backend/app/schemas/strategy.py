from pydantic import BaseModel


class StrategyInfo(BaseModel):
    name: str
    description: str
    params: dict[str, object]


class StrategyListResponse(BaseModel):
    strategies: list[StrategyInfo]


class CompositeStrategyRequest(BaseModel):
    """Request to build a composite strategy for backtest."""
    strategies: list[str]  # e.g. ["rsi_oversold", "bias_reversal"]
    mode: str = "majority"  # "all", "any", "majority"
    params: dict[str, dict[str, object]] = {}  # per-strategy params, e.g. {"rsi_oversold": {"period": 10}}
