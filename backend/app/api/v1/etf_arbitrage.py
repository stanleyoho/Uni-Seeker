"""GET /api/v1/etf-arbitrage/* — ETF premium / discount monitor.

Models the twetf.com core feature: estimated NAV vs market price.

    premium% = (market_price - estimated_nav) / estimated_nav * 100

See ``app.modules.etf_arbitrage`` for the actual computation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.etf_arbitrage import ETFArbitrageService
from app.modules.etf_arbitrage.classifier import ETF_TYPES
from app.obs.logging import get_logger
from app.schemas.etf_arbitrage import (
    ETFArbitrageKpiSchema,
    ETFArbitrageListResponse,
    ETFArbitrageRowSchema,
    ETFArbitrageStatsSchema,
)

logger = get_logger(component="etf_arbitrage")

router = APIRouter(prefix="/etf-arbitrage", tags=["etf-arbitrage"])

# The set of valid `type` query values. ``all`` short-circuits filtering.
_TYPE_VALUES = ("all", *ETF_TYPES)
_TypeQuery = Literal["all", "股票型", "主動式", "債券型", "槓桿反向"]
_DirectionQuery = Literal["all", "premium", "discount"]


def _get_service() -> ETFArbitrageService:
    """FastAPI dependency — overridable in tests to inject a stubbed
    FinMind provider without monkey-patching module-level state."""
    return ETFArbitrageService()


@router.get("/list", response_model=ETFArbitrageListResponse)
async def list_etf_arbitrage(
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[ETFArbitrageService, Depends(_get_service)],
    market: str = Query(default="TW", description="TW only for v1"),
    # `type` shadows a Python builtin; use `type_filter` internally and
    # expose the public query name via `alias`.
    type_filter: _TypeQuery = Query(
        default="all",
        alias="type",
        description="ETF type filter",
    ),
    direction: _DirectionQuery = Query(default="all", description="premium / discount / all"),
    limit: int = Query(default=50, ge=1, le=500),
) -> ETFArbitrageListResponse:
    """Return ETF premium/discount rows + market-wide stats.

    Empty `data` with a populated `message` indicates the FinMind NAV
    dataset is unavailable for the current account tier or trading
    session. The frontend renders a labelled empty state in that case
    instead of zero-filling. **We never fabricate NAV numbers.**
    """
    rows, stats, message = await service.list_etfs(
        db,
        market=market,
        type_filter=type_filter,
        direction=direction,
        limit=limit,
    )
    return ETFArbitrageListResponse(
        data=[ETFArbitrageRowSchema(**row.to_dict()) for row in rows],
        stats=ETFArbitrageStatsSchema(
            total_monitored=stats.total_monitored,
            premium_count=stats.premium_count,
            discount_count=stats.discount_count,
            max_premium_etf=ETFArbitrageKpiSchema(**stats.max_premium_etf)
            if stats.max_premium_etf
            else None,
            max_discount_etf=ETFArbitrageKpiSchema(**stats.max_discount_etf)
            if stats.max_discount_etf
            else None,
            market_sentiment=stats.market_sentiment,
            buffett_indicator=stats.buffett_indicator,
            data_source=stats.data_source,
        ),
        message=message,
    )
