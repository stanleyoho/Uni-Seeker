"""Portfolio dividend endpoints — /api/v1/holdings/dividends.

Spec §5.4 Table 3 + §9 (Phase 2 Batch C). Same thin-translator pattern
as `accounts.py` / `trades.py`:

- Endpoint guard: `tier_guard(feature="dividends")` — first line of the
  spec §9 雙保險. Blocks FREE tier at the FastAPI dependency layer with
  ``403 feature_unavailable:dividends`` BEFORE the service is touched.
- Service-level guard: `PortfolioDividendService._assert_dividends_feature`
  is the second line — it raises `TierFeatureUnavailable` if a programmer
  ever forgets the dependency. We translate to the same 403 detail
  string so the frontend contract is identical regardless of which
  guard fires.

There is no numeric quota for dividends in `tier_limits.yaml`; the
feature flag alone is enough. No `count_provider` is wired in.

`ValueError` translation
------------------------
The service raises plain `ValueError` for two distinct conditions:
1. Invalid dividend input on POST (unsupported `dividend_type`, missing
   `amount_per_share` for CASH, missing `ratio` for STOCK, etc.).
2. Attempt to PATCH an immutable field (anything other than `note` /
   `pay_date` / `withholding_tax`).
We map both to 422 but distinguish via the `detail` string:
`invalid_dividend_input` for the create path and
`immutable_dividend_field` for the patch path. This keeps the frontend
able to render distinct error toasts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.auth import require_auth
from app.modules.billing.tier_limits import tier_guard
from app.schemas.holdings.dividend import (
    DividendCreateRequest,
    DividendResponse,
    DividendUpdateRequest,
)
from app.services.portfolio import PortfolioDividendService
from app.services.portfolio.dividend_service import PortfolioDividendNotFoundError
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/dividends",
    response_model=DividendResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        # Feature-flag-only guard. No numeric quota → no count_provider.
        Depends(tier_guard(feature="dividends")),
    ],
)
async def create_dividend(
    body: DividendCreateRequest,
    db: DbDep,
    user: UserDep,
) -> DividendResponse:
    """Record a CASH or STOCK dividend event.

    Service-layer responsibilities:
      * Tier assertion (`dividends` feature flag, spec §9 第二層)
      * Account ownership verification (404 on miss / cross-user)
      * Insert dividend row
      * CASH → accrue `net_amount` to `positions.realized_pnl`
      * STOCK → scale every open lot by `(1 + ratio)` and re-upsert position
      * Emit `portfolio_dividend_recorded` audit event
    """
    service = PortfolioDividendService(db, user)  # type: ignore[arg-type]
    try:
        dividend = await service.record_dividend(
            account_id=body.account_id,
            symbol=body.symbol,
            market=body.market,
            dividend_type=body.dividend_type,
            ex_dividend_date=body.ex_dividend_date,
            pay_date=body.pay_date,
            amount_per_share=body.amount_per_share,
            quantity_at_record=body.quantity_at_record,
            ratio=body.ratio,
            currency=body.currency,
            withholding_tax=body.withholding_tax,
            note=body.note,
        )
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except TierFeatureUnavailable as exc:
        # Defensive: the dependency-layer guard should have caught this
        # already. Keep the branch so the contract is total when
        # `enable_monetization` toggling diverges between layers.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except ValueError as exc:
        # Service raises ValueError for invalid dividend_type, missing
        # branch-specific field (amount_per_share / ratio), or non-positive
        # quantity. Pydantic catches most of these at the DTO layer; this
        # branch covers the "valid DTO, invalid combination" cases.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INVALID_DIVIDEND_INPUT,
        ) from exc
    await db.commit()
    await db.refresh(dividend)
    return DividendResponse.model_validate(dividend)


@router.get(
    "/dividends",
    response_model=list[DividendResponse],
)
async def list_dividends(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(
        default=None,
        description="Optional account filter; omit to list across all owned accounts.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[DividendResponse]:
    """List dividends scoped to the user.

    `account_id` is optional — when supplied, the service verifies
    ownership and returns an empty list for cross-user / unknown ids
    (deliberate to avoid leaking existence). Pagination is applied here
    rather than in the service layer because the service was designed to
    return a snapshot list for offline contexts (audit, CLI export); the
    HTTP layer slices the resulting tail.
    """
    service = PortfolioDividendService(db, user)  # type: ignore[arg-type]
    rows = await service.list_dividends(account_id=account_id)
    # In-memory slice. The list_by_user / list_by_account repo queries
    # are already user-scoped; for Phase 2 user volumes (BASIC cap 200
    # trades/month, dividends rarer than trades) this is fine. Phase 3+
    # can push limit/offset into the repo if profiling demands it.
    sliced = rows[offset : offset + limit]
    return [DividendResponse.model_validate(r) for r in sliced]


@router.get(
    "/dividends/{dividend_id}",
    response_model=DividendResponse,
)
async def get_dividend(
    dividend_id: int,
    db: DbDep,
    user: UserDep,
) -> DividendResponse:
    """Fetch one owned dividend; 404 when missing / not owned."""
    service = PortfolioDividendService(db, user)  # type: ignore[arg-type]
    try:
        row = await service.get_dividend(dividend_id)
    except PortfolioDividendNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.DIVIDEND_NOT_FOUND,
        ) from exc
    return DividendResponse.model_validate(row)


@router.patch(
    "/dividends/{dividend_id}",
    response_model=DividendResponse,
)
async def update_dividend(
    dividend_id: int,
    body: DividendUpdateRequest,
    db: DbDep,
    user: UserDep,
) -> DividendResponse:
    """PATCH a dividend; only `note` / `pay_date` / `withholding_tax` accepted.

    Any other key surfaced via the body triggers `ValueError` from the
    service, which we translate to 422 with detail
    `immutable_dividend_field` so the frontend can render a "delete +
    recreate to change amount" hint.
    """
    service = PortfolioDividendService(db, user)  # type: ignore[arg-type]
    patch = body.model_dump(exclude_unset=True)
    try:
        updated = await service.update_dividend(dividend_id, **patch)
    except PortfolioDividendNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.DIVIDEND_NOT_FOUND,
        ) from exc
    except TierFeatureUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.IMMUTABLE_DIVIDEND_FIELD,
        ) from exc
    await db.commit()
    await db.refresh(updated)
    return DividendResponse.model_validate(updated)


@router.delete(
    "/dividends/{dividend_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_dividend(
    dividend_id: int,
    db: DbDep,
    user: UserDep,
) -> None:
    """Delete a dividend row.

    Phase 2 MVP: cost-basis side effects from the original record are
    NOT reversed (see service docstring). 204 No Content on success
    matches the wider REST convention; the frontend keys off the status
    code rather than a body.
    """
    service = PortfolioDividendService(db, user)  # type: ignore[arg-type]
    try:
        await service.delete_dividend(dividend_id)
    except PortfolioDividendNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.DIVIDEND_NOT_FOUND,
        ) from exc
    except TierFeatureUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    await db.commit()
    return None
