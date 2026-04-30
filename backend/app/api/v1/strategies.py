from fastapi import APIRouter

from app.modules.strategy import create_default_registry
from app.schemas.strategy import StrategyInfo, StrategyListResponse

router = APIRouter(prefix="/strategies", tags=["strategies"])

_registry = create_default_registry()


@router.get("/", response_model=StrategyListResponse)
def list_strategies() -> StrategyListResponse:
    strategies = [
        StrategyInfo(
            name=info["key"],
            description=str(info["description"]),
            params=info["params"],
        )
        for info in _registry.list_info()
    ]
    return StrategyListResponse(strategies=strategies)
