"""Summary endpoints — /api/v1/holdings/summary.

Spec §5.4 + §7.4. Returns user-wide or per-account KPI rows. The
domain `PortfolioSummary` has six numeric fields; we augment with
`position_count` + `account_count` for frontend convenience.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.schemas.holdings.summary import SummaryResponse
from app.services.portfolio import PortfolioSummaryService
from app.services.portfolio.exceptions import PortfolioAccountNotFound

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


@router.get(
    "/summary",
    response_model=SummaryResponse,
)
async def get_user_summary(
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> SummaryResponse:
    """KPI row aggregated across every account the user owns."""
    service = PortfolioSummaryService(db, user, fetcher)  # type: ignore[arg-type]
    summary = await service.get_user_summary()
    # Position / account counts are convenience metadata, not part of
    # the domain summary. Pull them through the same repos the service
    # already uses — both queries are O(rows) and the path is read-only.
    position_count = await PortfolioPositionRepo(db).count_by_user(
        user.id  # type: ignore[attr-defined]
    )
    account_count = await PortfolioAccountRepo(db).count_by_user(
        user.id  # type: ignore[attr-defined]
    )
    return SummaryResponse(
        total_cost=summary.total_cost,
        total_value=summary.total_value,
        total_unrealized_pnl=summary.total_unrealized_pnl,
        total_daily_change=summary.total_daily_change,
        gain_simple=summary.gain_simple,
        gain_simple_pct=summary.gain_simple_pct,
        position_count=position_count,
        account_count=account_count,
    )


@router.get(
    "/summary/{account_id}",
    response_model=SummaryResponse,
)
async def get_account_summary(
    account_id: int,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> SummaryResponse:
    """KPI row scoped to one of the user's accounts; 404 when missing
    / not owned."""
    service = PortfolioSummaryService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        summary = await service.get_account_summary(account_id)
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    # For per-account summary, position count is scoped to the account.
    positions = await PortfolioPositionRepo(db).list_by_account(account_id)
    return SummaryResponse(
        total_cost=summary.total_cost,
        total_value=summary.total_value,
        total_unrealized_pnl=summary.total_unrealized_pnl,
        total_daily_change=summary.total_daily_change,
        gain_simple=summary.gain_simple,
        gain_simple_pct=summary.gain_simple_pct,
        position_count=len(positions),
        account_count=1,
    )
