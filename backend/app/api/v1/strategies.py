from fastapi import APIRouter

from app.modules.strategy.builtin import MACrossoverStrategy, RSIOversoldStrategy
from app.schemas.strategy import StrategyInfo, StrategyListResponse

router = APIRouter(prefix="/strategies", tags=["strategies"])

BUILTIN_STRATEGIES = {
    "ma_crossover": MACrossoverStrategy,
    "rsi_oversold": RSIOversoldStrategy,
}


@router.get("/", response_model=StrategyListResponse)
def list_strategies() -> StrategyListResponse:
    strategies = []
    for key, cls in BUILTIN_STRATEGIES.items():
        instance = cls()
        strategies.append(StrategyInfo(
            name=key,
            description=instance.config.description,
            params=instance.config.params,
        ))
    return StrategyListResponse(strategies=strategies)
