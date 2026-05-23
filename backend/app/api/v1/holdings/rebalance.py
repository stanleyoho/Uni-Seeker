"""Portfolio rebalancing endpoints — /api/v1/holdings/rebalance/*.

Spec: Portfolio Phase 5+. Pro-tier only. The endpoint is preview-only —
no trades are persisted; the user reviews the suggestion in the UI and
chooses whether to apply (by walking each suggested trade through the
existing ``POST /holdings/trades`` flow).

Tier gating uses the standard 双保险 pattern (spec §9):
  - ``Depends(tier_guard(feature="rebalancing"))`` short-circuits with 403
    before the service even runs.
  - Inside ``RebalancingService.preview_rebalance`` the same flag is
    re-asserted; if the dependency were ever forgotten, this raises
    ``TierFeatureUnavailable`` which we translate to 403 with the
    standard ``feature_unavailable:rebalancing`` detail string.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.modules.billing.tier_limits import tier_guard
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.schemas.holdings.rebalance import (
    RebalanceRequest,
    RebalanceResponse,
    SuggestedTradeResponse,
)
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)
from app.services.portfolio.rebalancing_service import RebalancingService

router = APIRouter(prefix="/rebalance", tags=["holdings.rebalance"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


@router.post(
    "/preview",
    response_model=RebalanceResponse,
    dependencies=[Depends(tier_guard(feature="rebalancing"))],
)
async def preview_rebalance(
    body: RebalanceRequest,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> RebalanceResponse:
    """Compute the trades required to reach ``body.targets``.

    Errors:
        - 403 ``feature_unavailable:rebalancing`` when the user's tier
          lacks the feature flag (the guard catches this first; the
          inner assert is the backup).
        - 404 ``portfolio_account_not_found`` when ``account_id`` is set
          and not owned by the user.
        - 422 ``invalid_rebalance_input`` when targets fail validation
          (sum != 100, duplicates, negatives, etc.).
    """
    service = RebalancingService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        result = await service.preview_rebalance(
            targets=[t.model_dump() for t in body.targets],
            account_id=body.account_id,
            min_trade_value=body.min_trade_value,
        )
    except TierFeatureUnavailable as exc:
        # Defensive: should be caught by the dependency above. Keep the
        # translation so a future refactor (e.g. swapping the dep out)
        # still returns the right status.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        # Raised by ``validate_targets``: sum mismatch, negatives, dupes.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_rebalance_input",
        ) from exc

    # Translate domain dataclasses → Pydantic response.
    return RebalanceResponse(
        total_portfolio_value=result.total_portfolio_value,
        suggested_trades=[
            SuggestedTradeResponse(
                symbol=t.symbol,
                market=t.market,  # type: ignore[arg-type]  # str → Market via use_enum_values
                action=t.action,
                qty=t.qty,
                estimated_price=t.estimated_price,
                estimated_value=t.estimated_value,
                rationale=t.rationale,
            )
            for t in result.suggested_trades
        ],
        final_allocation_pct=result.final_allocation_pct,
        skipped_trades=result.skipped_trades,
        cash_residual=result.cash_residual,
    )


__all__ = ["router"]
