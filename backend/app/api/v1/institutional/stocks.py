"""Cross-stock institutional view — /api/v1/institutional/stocks/{symbol}.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5.5 (cross-stock view) + §8 (`institutional_ownership_panel` Pro-only).

Tier guard is service-side only (not declarative): the service's
`_assert_feature` raises `F13TierFeatureUnavailable` which we map to
403. We keep the second-line guard in the service because the count-
based dep-layer `tier_guard` factory is over-engineered for a simple
feature flag and would conflict with the count_provider contract.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.institutional import _detail as detail
from app.auth import require_auth
from app.models.stock import Stock
from app.schemas.institutional.cross_stock import (
    F13InstitutionalHolderForStock,
    F13InstitutionalStockResponse,
)
from app.services.institutional import (
    F13CrossStockService,
    F13TierFeatureUnavailable,
)

router = APIRouter(prefix="/stocks", tags=["institutional.stocks"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]


@router.get(
    "/{symbol}/institutional",
    response_model=F13InstitutionalStockResponse,
)
async def get_institutional_for_stock(
    symbol: str,
    db: DbDep,
    user: UserDep,
    limit: int = Query(50, ge=1, le=200),
) -> F13InstitutionalStockResponse:
    """Per-stock institutional ownership panel (Pro-only).

    Returns the list of filers that hold this symbol with their latest
    position + a coarse change-type indicator. Lower-tier users get a
    403 with `feature_unavailable:institutional_ownership_panel`.
    """
    svc = F13CrossStockService(db, user)  # type: ignore[arg-type]
    try:
        holders = await svc.get_institutional_holders_for_stock(symbol=symbol, limit=limit)
    except F13TierFeatureUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc

    # Resolve stock_id for the envelope (may be None when the symbol
    # has no `stocks` row yet but holdings exist by CUSIP).
    stock_row = await db.execute(select(Stock.id).where(Stock.symbol == symbol))
    stock_id = stock_row.scalar_one_or_none()

    return F13InstitutionalStockResponse(
        symbol=symbol,
        stock_id=stock_id,
        holders=[
            F13InstitutionalHolderForStock(
                filer_id=h["filer_id"],
                filer_name=h["filer_name"],
                filer_cik=h["filer_cik"],
                latest_shares=h.get("latest_shares"),
                latest_value_usd=h.get("latest_value_usd"),
                prev_shares=h.get("prev_shares"),
                change_type=h.get("change_type", "UNCHANGED"),
            )
            for h in holders
        ],
    )
