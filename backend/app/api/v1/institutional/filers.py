"""Filer + subscription endpoints — /api/v1/institutional/filers.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5.1 + §5.2 + §5.5 (refresh) + §8 (tier guards).

Endpoints translate F13 domain exceptions (raised by
`app.services.institutional.*`) to HTTP status codes via
`app.api.v1.institutional._detail`. Tier enforcement is doubled per
spec §9:
  1. Dependency-layer `tier_guard(...)` — declarative, fails fast.
  2. Service-layer assertions raise domain exceptions caught here.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.institutional import _detail as detail
from app.api.v1.institutional._deps import (
    get_edgar_client,
    tracked_filers_count_provider,
)
from app.auth import require_auth
from app.db.models.institutional.subscription import F13UserSubscription
from app.modules.billing.tier_limits import tier_guard
from app.modules.institutional.edgar_client import EdgarClient
from app.schemas.institutional.filer import (
    F13FilerResponse,
    F13FilerSearchResult,
)
from app.schemas.institutional.filing import F13RefreshResponse
from app.schemas.institutional.subscription import (
    F13BulkSubscribeError,
    F13BulkSubscribeRequest,
    F13BulkSubscribeResponse,
    F13SubscribeRequest,
    F13SubscriptionPreferencesResponse,
    F13SubscriptionPreferencesUpdate,
    F13SubscriptionResponse,
)
from app.services.institutional import (
    F13EdgarError,
    F13FilerNotFound,
    F13FilerSearchService,
    F13FilingService,
    F13RefreshInFlight,
    F13SubscriptionExists,
    F13SubscriptionService,
    F13TierFeatureUnavailable,
    F13TierLimitExceeded,
)

router = APIRouter(prefix="/filers", tags=["institutional.filers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
EdgarDep = Annotated[EdgarClient, Depends(get_edgar_client)]


# ── helpers ────────────────────────────────────────────────────────────


def _translate_tier_exc(exc: Exception) -> HTTPException:
    """Map service-layer tier domain exceptions to HTTP 403.

    Both `F13TierLimitExceeded` and `F13TierFeatureUnavailable` are
    403; the detail string is the contract the frontend asserts on.
    """
    if isinstance(exc, F13TierLimitExceeded):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.limit_exceeded(exc.limit_key),
        )
    if isinstance(exc, F13TierFeatureUnavailable):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        )
    raise exc  # pragma: no cover - defensive


async def _subscription_meta(
    db: AsyncSession, user_id: int, filer_id: int
) -> F13UserSubscription | None:
    """Reach into `f13_user_subscriptions` for the `subscribed_at` /
    `notify_on_new_filing` fields needed by `F13SubscriptionResponse`.

    Service layer returns the filer ORM row only; this helper bridges
    so the API layer can hand the frontend everything in one payload
    without leaking another service method just for two columns.
    """
    result = await db.execute(
        select(F13UserSubscription).where(
            F13UserSubscription.user_id == user_id,
            F13UserSubscription.filer_id == filer_id,
        )
    )
    return result.scalar_one_or_none()


# ── endpoints ──────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=F13SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        # Spec §9 first-line declarative guard. Service layer re-checks.
        Depends(
            tier_guard(
                limit_key="max_tracked_filers",
                current_count_provider=tracked_filers_count_provider,
            )
        ),
    ],
)
async def subscribe_filer(
    db: DbDep,
    user: UserDep,
    body: F13SubscribeRequest = Body(...),
) -> F13SubscriptionResponse:
    """Subscribe the current user to a filer identified by CIK.

    Behaviour:
      - CIK already mapped to a local filer → just insert subscription.
      - CIK new → create the filer row first (requires `name`).
      - Already subscribed → 409 with `f13_subscription_exists` detail.
    """
    svc = F13SubscriptionService(db, user)  # type: ignore[arg-type]
    try:
        filer = await svc.subscribe(
            cik_or_filer_id=body.cik,
            name=body.name,
            legal_name=body.legal_name,
        )
    except (F13TierLimitExceeded, F13TierFeatureUnavailable) as exc:
        raise _translate_tier_exc(exc) from exc
    except F13SubscriptionExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.F13_SUBSCRIPTION_EXISTS,
        ) from exc
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail.F13_INVALID_INPUT,
        ) from exc
    await db.commit()
    await db.refresh(filer)

    sub = await _subscription_meta(db, user.id, filer.id)  # type: ignore[attr-defined]
    return F13SubscriptionResponse(
        filer=F13FilerResponse.model_validate(filer),
        subscribed_at=sub.subscribed_at if sub else filer.created_at,
        notify_on_new_filing=sub.notify_on_new_filing if sub else True,
    )


@router.post(
    "/bulk",
    response_model=F13BulkSubscribeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_subscribe_filers(
    req: F13BulkSubscribeRequest,
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
) -> F13BulkSubscribeResponse:
    """Bulk-subscribe up to 20 filers atomically.

    Tier quota: atomic pre-check at the service layer
    (`F13SubscriptionService.bulk_subscribe` projects current + new
    unique CIKs against `max_tracked_filers` BEFORE any INSERT). Over
    quota → 403 with `limit_exceeded:max_tracked_filers`; the whole
    batch is rejected, no partial commits.

    Per-row issues land in `errors[]` inside the 201 envelope:
      - `invalid_cik`          — failed CIK normalisation
      - `edgar_lookup_failed`  — name missing + EDGAR fetch failed
    These NEVER short-circuit the call.

    We deliberately skip the dependency-layer `tier_guard(...)` here
    because that guard increments the count by 1, which would block
    a Free user from any bulk attempt even when the batch fits. The
    service layer's atomic check is the single source of truth.
    """
    svc = F13SubscriptionService(db, user, edgar)  # type: ignore[arg-type]
    try:
        result = await svc.bulk_subscribe(
            items=[item.model_dump() for item in req.items],
        )
    except (F13TierLimitExceeded, F13TierFeatureUnavailable) as exc:
        # Tier check fires BEFORE any INSERT — no rollback needed.
        # Calling db.rollback() here would expire other ORM rows
        # (e.g. the requesting user) and break callers that hold
        # references across the call boundary.
        raise _translate_tier_exc(exc) from exc
    except F13SubscriptionExists as exc:
        # Race: a parallel single-subscribe slipped a row in between
        # the service's de-dup check and the INSERT. Roll back partial
        # batch state and return 409.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail.F13_SUBSCRIPTION_EXISTS,
        ) from exc
    except ValueError as exc:
        # Defensive: only fires for our explicit "> 20 items" guard
        # in the service which Pydantic already enforces. Service has
        # not flushed any INSERT yet.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail.F13_INVALID_INPUT,
        ) from exc

    await db.commit()

    # Refresh inserted filers so latest_* columns are present in the response.
    for filer in result["subscribed"]:
        await db.refresh(filer)

    return F13BulkSubscribeResponse(
        subscribed=[
            F13FilerResponse.model_validate(f) for f in result["subscribed"]
        ],
        skipped_duplicates=list(result["skipped_duplicates"]),
        errors=[
            F13BulkSubscribeError(**e) for e in result["errors"]
        ],
    )


@router.get(
    "",
    response_model=list[F13FilerResponse],
)
async def list_subscriptions(
    db: DbDep,
    user: UserDep,
) -> list[F13FilerResponse]:
    """List filers the current user is subscribed to (alphabetical)."""
    svc = F13SubscriptionService(db, user)  # type: ignore[arg-type]
    filers = await svc.list_subscriptions()
    return [F13FilerResponse.model_validate(f) for f in filers]


@router.post(
    "/search",
    response_model=list[F13FilerSearchResult],
)
async def search_filers(
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=50),
) -> list[F13FilerSearchResult]:
    """Search filers by name across local DB + EDGAR fulltext.

    EDGAR augmentation degrades gracefully — a transient EDGAR failure
    returns the local-only list (service layer logs the warning) and
    never raises here. Hit shape: `{cik, name, legal_name,
    is_locally_known}`.
    """
    svc = F13FilerSearchService(db, user, edgar)  # type: ignore[arg-type]
    hits = await svc.search_filers(q, limit=limit)
    return [F13FilerSearchResult.model_validate(h) for h in hits]


@router.get(
    "/{filer_id}",
    response_model=F13FilerResponse,
)
async def get_filer(
    filer_id: int,
    db: DbDep,
    user: UserDep,
) -> F13FilerResponse:
    """Fetch a subscribed filer; 404 when missing OR not subscribed.

    "Not subscribed" collapses to 404 by convention (information
    hiding) — same shape as the portfolio module's
    `PortfolioAccountNotFound`.
    """
    svc = F13SubscriptionService(db, user)  # type: ignore[arg-type]
    if not await svc.get_subscription_status(filer_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        )
    # Subscribed → fetch through the repo path the service holds.
    filer = await svc._filer_repo.get_by_id(filer_id)  # type: ignore[attr-defined]
    if filer is None:  # pragma: no cover - subscribed but row missing == invariant violation
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        )
    return F13FilerResponse.model_validate(filer)


@router.delete(
    "/{filer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unsubscribe_filer(
    filer_id: int,
    db: DbDep,
    user: UserDep,
) -> None:
    """Remove the (user, filer) subscription.

    404 when the subscription wasn't found (same collapse as
    `get_filer`). Returns 204 on success — no body.
    """
    svc = F13SubscriptionService(db, user)  # type: ignore[arg-type]
    try:
        await svc.unsubscribe(filer_id)
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    await db.commit()
    return None


@router.patch(
    "/{filer_id}/preferences",
    response_model=F13SubscriptionPreferencesResponse,
    status_code=status.HTTP_200_OK,
)
async def update_filer_preferences(
    filer_id: int,
    body: F13SubscriptionPreferencesUpdate,
    db: DbDep,
    user: UserDep,
) -> F13SubscriptionPreferencesResponse:
    """Toggle ``notify_on_new_filing`` for an existing subscription.

    404 when the user is not subscribed to ``filer_id`` (same info-
    hiding collapse as ``GET /filers/{id}`` — we do not reveal whether
    the filer exists if the caller isn't subscribed).
    """
    sub = await _subscription_meta(db, user.id, filer_id)  # type: ignore[attr-defined]
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        )
    sub.notify_on_new_filing = body.notify_on_new_filing
    await db.commit()
    await db.refresh(sub)
    return F13SubscriptionPreferencesResponse(
        filer_id=filer_id,
        notify_on_new_filing=sub.notify_on_new_filing,
    )


@router.post(
    "/{filer_id}/refresh",
    response_model=F13RefreshResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_filer(
    filer_id: int,
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
    max_quarters: int = Query(4, ge=1, le=4),
) -> F13RefreshResponse:
    """Refresh the latest N (≤4) 13F filings on-demand (Q1 + Q8).

    Anti-concurrency: a second simultaneous refresh on the same filer
    raises `F13RefreshInFlight` which we translate to 429. EDGAR
    failures (after retries) become 502 with the upstream status
    preserved on a best-effort basis.
    """
    svc = F13FilingService(db, user, edgar)  # type: ignore[arg-type]
    try:
        result = await svc.refresh_filer(
            filer_id=filer_id, max_quarters=max_quarters
        )
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    except F13RefreshInFlight as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail.F13_REFRESH_IN_FLIGHT,
        ) from exc
    except F13EdgarError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail.F13_EDGAR_ERROR,
            headers=(
                {"X-Edgar-Status": str(exc.edgar_status)}
                if exc.edgar_status is not None
                else None
            ),
        ) from exc
    await db.commit()
    return F13RefreshResponse(**result)
