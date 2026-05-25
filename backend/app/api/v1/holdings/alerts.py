"""User-defined alert rule endpoints — /api/v1/holdings/alerts.

UNI-ALERT-001. Endpoints stay thin: instantiate ``AlertService``,
translate domain exceptions to HTTP via ``_detail``.

Tier enforcement (双保险, mirrors /accounts):
  1. Dependency-layer ``tier_guard(limit_key="max_alert_rules")`` on
     the create endpoint — declarative, fails fast.
  2. Service-layer re-check in ``AlertService.create_rule`` — final
     authority even if a future programmer forgets the dependency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._count_providers import alert_rule_count_provider
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.modules.billing.tier_limits import tier_guard
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.schemas.holdings.alert import (
    AlertEvaluationResponse,
    AlertRuleCreateRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
)
from app.services.alerts.alert_service import (
    AlertRuleNotFoundError,
    AlertService,
    InvalidAlertRuleError,
)
from app.services.portfolio.exceptions import (
    TierFeatureUnavailable,
    TierLimitExceeded,
)

router = APIRouter(prefix="/alerts", tags=["holdings.alerts"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


def _translate_tier_exc(exc: Exception) -> HTTPException:
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


@router.post(
    "",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            tier_guard(
                limit_key="max_alert_rules",
                current_count_provider=alert_rule_count_provider,
            )
        ),
    ],
)
async def create_alert_rule(
    body: AlertRuleCreateRequest,
    db: DbDep,
    user: UserDep,
) -> AlertRuleResponse:
    service = AlertService(db, user)  # type: ignore[arg-type]
    try:
        rule = await service.create_rule(
            name=body.name,
            rule_type=body.rule_type,
            threshold_value=body.threshold_value,
            threshold_type=body.threshold_type,
            symbol=body.symbol,
            market=body.market,
        )
    except InvalidAlertRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{detail.INVALID_ALERT_RULE}:{exc.code}",
        ) from exc
    except (TierLimitExceeded, TierFeatureUnavailable) as exc:
        raise _translate_tier_exc(exc) from exc
    await db.commit()
    await db.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.get("", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    db: DbDep,
    user: UserDep,
) -> list[AlertRuleResponse]:
    service = AlertService(db, user)  # type: ignore[arg-type]
    rules = await service.list_rules()
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.patch("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    body: AlertRuleUpdateRequest,
    db: DbDep,
    user: UserDep,
) -> AlertRuleResponse:
    service = AlertService(db, user)  # type: ignore[arg-type]
    patch = body.model_dump(exclude_unset=True)
    try:
        rule = await service.update_rule(rule_id, **patch)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ALERT_RULE_NOT_FOUND,
        ) from exc
    except InvalidAlertRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{detail.INVALID_ALERT_RULE}:{exc.code}",
        ) from exc
    await db.commit()
    await db.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_alert_rule(
    rule_id: int,
    db: DbDep,
    user: UserDep,
) -> dict[str, bool]:
    service = AlertService(db, user)  # type: ignore[arg-type]
    try:
        await service.delete_rule(rule_id)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ALERT_RULE_NOT_FOUND,
        ) from exc
    await db.commit()
    return {"ok": True}


@router.post(
    "/{rule_id}/evaluate",
    response_model=AlertEvaluationResponse,
)
async def evaluate_alert_rule(
    rule_id: int,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> AlertEvaluationResponse:
    """Manual evaluation trigger (Pro "evaluate now").

    Tier-gating note: Free users will already be blocked by the
    ``max_alert_rules=0`` quota on rule creation, so by the time a rule
    exists the user already has the tier. We therefore do NOT add an
    extra feature flag here — the rule's existence IS the entitlement.
    """
    service = AlertService(db, user)  # type: ignore[arg-type]
    try:
        result = await service.evaluate_one(rule_id, fetcher)
    except AlertRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ALERT_RULE_NOT_FOUND,
        ) from exc
    await db.commit()
    return AlertEvaluationResponse(**result)  # type: ignore[arg-type]


__all__ = ["router"]
