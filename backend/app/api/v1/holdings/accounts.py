"""Portfolio account endpoints — /api/v1/holdings/accounts.

Spec §5.4 Table 1 + §9 (declarative tier_guard + service-level second
line). Endpoints stay thin: instantiate `PortfolioAccountService`,
translate domain exceptions to HTTP status codes via
`app.api.v1.holdings._detail`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._count_providers import account_count_provider
from app.auth import require_auth
from app.modules.billing.tier_limits import tier_guard
from app.schemas.holdings.account import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
)
from app.services.portfolio import PortfolioAccountService
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
    TierLimitExceeded,
)

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]


# ── helpers ─────────────────────────────────────────────────────────────────


def _translate_tier_exc(exc: Exception) -> HTTPException:
    """Map service-layer tier domain exceptions to HTTP 403.

    Both `TierLimitExceeded` and `TierFeatureUnavailable` are 403; the
    detail string is the contract the frontend asserts on.
    """
    if isinstance(exc, TierLimitExceeded):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.limit_exceeded(exc.limit_key),
        )
    if isinstance(exc, TierFeatureUnavailable):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        )
    raise exc  # pragma: no cover - defensive


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        # NOTE: `multi_account` is intentionally NOT enforced at the
        # dependency layer. The feature gates the *second-and-onwards*
        # account — FREE users with zero accounts MUST be allowed to
        # create their first one. The dependency-layer `tier_guard` has
        # no "first one free" semantic, so multi-account is handled by
        # the service-level second line (`PortfolioAccountService._assert
        # _multi_account_feature`) and translated to 403 below.
        Depends(
            tier_guard(
                limit_key="max_accounts",
                current_count_provider=account_count_provider,
            )
        ),
    ],
)
async def create_account(
    body: AccountCreateRequest,
    db: DbDep,
    user: UserDep,
) -> AccountResponse:
    """Create a new portfolio account.

    Tier enforcement is doubled per spec §9:
      1. `tier_guard` dependency above — declarative, fails fast (403)
         when the user is FREE and already has one account
         (`multi_account=false`) OR is over `max_accounts`.
      2. `PortfolioAccountService.create_account` re-checks both
         conditions; if a programmer ever forgets the dependency, the
         service still raises `TierFeatureUnavailable` /
         `TierLimitExceeded` which we translate to 403 here.
    """
    service = PortfolioAccountService(db, user)  # type: ignore[arg-type]
    try:
        account = await service.create_account(
            name=body.name,
            market=body.market,
            broker=body.broker,
            currency=body.currency,
            description=body.description,
        )
    except (TierLimitExceeded, TierFeatureUnavailable) as exc:
        raise _translate_tier_exc(exc) from exc
    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
)
async def list_accounts(
    db: DbDep,
    user: UserDep,
) -> list[AccountResponse]:
    """List every account owned by the requesting user (oldest first)."""
    service = PortfolioAccountService(db, user)  # type: ignore[arg-type]
    accounts = await service.list_accounts()
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get(
    "/accounts/{account_id}",
    response_model=AccountResponse,
)
async def get_account(
    account_id: int,
    db: DbDep,
    user: UserDep,
) -> AccountResponse:
    """Fetch one owned account; 404 when missing / not owned."""
    service = PortfolioAccountService(db, user)  # type: ignore[arg-type]
    try:
        account = await service.get_account(account_id)
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    return AccountResponse.model_validate(account)


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountResponse,
)
async def update_account(
    account_id: int,
    body: AccountUpdateRequest,
    db: DbDep,
    user: UserDep,
) -> AccountResponse:
    """Patch allowed fields on an owned account."""
    service = PortfolioAccountService(db, user)  # type: ignore[arg-type]
    # Skip unset fields so the service doesn't overwrite with None.
    patch = body.model_dump(exclude_unset=True)
    try:
        updated = await service.update_account(account_id, **patch)
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    await db.commit()
    await db.refresh(updated)
    return AccountResponse.model_validate(updated)


@router.delete(
    "/accounts/{account_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_account(
    account_id: int,
    db: DbDep,
    user: UserDep,
) -> dict[str, bool]:
    """Delete an owned account; FK cascade removes trades / lots /
    positions transparently."""
    service = PortfolioAccountService(db, user)  # type: ignore[arg-type]
    try:
        await service.delete_account(account_id)
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    await db.commit()
    return {"ok": True}
