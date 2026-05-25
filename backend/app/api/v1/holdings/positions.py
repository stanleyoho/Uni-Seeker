"""Position endpoints — /api/v1/holdings/positions.

Spec §5.4 + §7. Service returns enriched `PositionWithPnL` dataclasses;
we flatten them into the wire schema declared in
`app.schemas.portfolio.position`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.models.enums import Market
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.schemas.holdings.position import (
    PositionListResponse,
    PositionResponse,
)
from app.services.portfolio import (
    PortfolioPositionService,
    PositionWithPnL,
)
from app.services.portfolio.exceptions import PortfolioAccountNotFoundError

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


def _to_response(p: PositionWithPnL) -> PositionResponse:
    """Flatten a `PositionWithPnL` (service-layer dataclass) into the
    wire DTO. Nested `unrealized_pnl` / `daily_change` are decomposed
    into their flat numeric fields; `None` propagates when the symbol
    had no live quote (§12 R8)."""
    return PositionResponse(
        account_id=p.account_id,
        symbol=p.symbol,
        market=p.market,
        currency=p.currency,
        qty=p.quantity,
        avg_cost=p.avg_cost,
        total_cost=p.total_cost,
        realized_pnl=p.realized_pnl,
        last_price=p.last_price,
        prev_close=p.prev_close,
        price_as_of=p.price_as_of,
        unrealized_pnl=(p.unrealized_pnl.unrealized_pnl if p.unrealized_pnl else None),
        unrealized_pnl_pct=(p.unrealized_pnl.unrealized_pnl_pct if p.unrealized_pnl else None),
        daily_change=(p.daily_change.delta_total if p.daily_change else None),
        daily_change_pct=(p.daily_change.delta_pct if p.daily_change else None),
        is_closed=p.is_closed,
    )


@router.get(
    "/positions",
    response_model=PositionListResponse,
)
async def list_positions(
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
    account_id: int | None = Query(default=None),
) -> PositionListResponse:
    """List positions for the user, optionally scoped to one account.

    Closed positions (qty=0) are included so the frontend can decide
    whether to hide them — same contract as the service layer.
    """
    service = PortfolioPositionService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        rows = await service.list_positions(account_id=account_id)
    except PortfolioAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    return PositionListResponse(
        account_id=account_id,
        positions=[_to_response(r) for r in rows],
    )


@router.get(
    "/positions/{account_id}/{symbol}",
    response_model=PositionResponse,
)
async def get_position(
    account_id: int,
    symbol: str,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
    market: Market = Query(...),
) -> PositionResponse:
    """Fetch one enriched position. `market` is required as a query
    parameter because (account_id, symbol, market) is the uniqueness
    key — `2330` on TWSE and on OTC are distinct holdings.
    """
    service = PortfolioPositionService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        row = await service.get_position(account_id, symbol, market=market)
    except PortfolioAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    return _to_response(row)


# silence unused-import lint — Decimal is referenced indirectly via the
# schema layer but mypy is happy if we keep it visible here.
_ = Decimal
