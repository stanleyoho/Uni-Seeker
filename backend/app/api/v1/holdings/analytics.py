"""Analytics endpoint — /api/v1/holdings/analytics.

Phase 5. Spec §11 (TWR / Sharpe extensibility) + Phase 5 brief.

Single GET that computes TWR / Sharpe / max-drawdown for a period.
Per spec §9 the tier gate is enforced *both* at the endpoint (via
`AnalyticsService.compute_period_analytics` raising
`TierFeatureUnavailable`) and the dependency layer would normally hook
`tier_guard(feature=...)` — for this endpoint we lean on the
service-level check only because the feature flag is the same one
already used by `summary` so we keep the response shape consistent
between "feature missing" and "no snapshots yet" cases.

Response codes:
  * 200 — analytics computed (may be empty / sharpe=None when there are
          fewer than 2 snapshots; this is **not** an error).
  * 403 — tier feature unavailable
  * 404 — account_id given but not owned by the user
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.schemas.holdings.analytics import AnalyticsResponse
from app.services.portfolio import AnalyticsService
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)

router = APIRouter(prefix="/analytics", tags=["holdings.analytics"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
    period: Literal["1m", "3m", "6m", "1y", "ytd", "all"] = Query(
        "1m",
        description="Lookback window for the analytics calculation.",
    ),
    account_id: int | None = Query(
        None,
        description=(
            "Filter to one account. Omit for the user-wide roll-up "
            "(reads snapshots with account_id IS NULL)."
        ),
    ),
) -> AnalyticsResponse:
    """TWR / Sharpe / max-drawdown for the requested period."""
    service = AnalyticsService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        result = await service.compute_period_analytics(period=period, account_id=account_id)
    except TierFeatureUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc

    return AnalyticsResponse(
        twr=result.twr,
        twr_annualized=result.twr_annualized,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown=result.max_drawdown,
        max_drawdown_pct=result.max_drawdown_pct,
        period_days=result.period_days,
        snapshot_count=result.snapshot_count,
    )


__all__ = ["router"]
