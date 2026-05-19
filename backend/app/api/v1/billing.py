from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import require_auth
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User
from app.modules.billing.stripe_service import StripeService
from app.obs.metrics import TIER_DOWNGRADE_TOTAL, TIER_UPGRADE_TOTAL
from app.schemas.billing import BillingStatusResponse, CheckoutRequest, CheckoutResponse
from app.services.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


def get_stripe_service() -> StripeService:
    """Inject price IDs from settings to avoid hardcoding inside the service."""
    return StripeService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        price_ids={
            "basic": settings.stripe_price_id_basic,
            "pro": settings.stripe_price_id_pro,
        },
    )


def _stripe_service_dep() -> StripeService:
    """Indirection layer so tests can ``@patch`` ``get_stripe_service`` and
    have FastAPI's ``Depends`` pick up the patched callable at request time.

    FastAPI captures the function object passed to ``Depends`` at import time,
    so patching the module-level name alone has no effect on dispatched
    dependencies. Routing through this wrapper makes the lookup dynamic.
    """
    from app.api.v1 import billing as _self

    return _self.get_stripe_service()


StripeServiceDep = Annotated[StripeService, Depends(_stripe_service_dep)]
CurrentUser = Annotated[User, Depends(require_auth)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    req: CheckoutRequest,
    current_user: CurrentUser,
    stripe_svc: StripeServiceDep,
    request: Request,
) -> CheckoutResponse:
    base = str(request.base_url).rstrip("/")
    try:
        url = stripe_svc.create_checkout_session(
            user_id=current_user.id,
            tier=req.tier,
            success_url=f"{base}/billing/success",
            cancel_url=f"{base}/billing/cancel",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CheckoutResponse(checkout_url=url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_svc: StripeServiceDep,
    stripe_signature: str = Header(alias="stripe-signature", default=""),
) -> Response:
    payload = await request.body()
    try:
        result = stripe_svc.handle_webhook(payload, stripe_signature)
    except ValueError as exc:
        logger.warning("Webhook signature error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc

    # Idempotency: Stripe delivers at-least-once. Dedupe by event_id using
    # INSERT ... ON CONFLICT DO NOTHING RETURNING. If RETURNING yields no row,
    # we've already processed this event and must skip the side effects.
    if result.event_id:
        insert_res = await db.execute(
            text(
                "INSERT INTO processed_webhook_events (event_id, event_type) "
                "VALUES (:eid, :etype) "
                "ON CONFLICT (event_id) DO NOTHING RETURNING event_id"
            ),
            {"eid": result.event_id, "etype": result.event_type},
        )
        if insert_res.first() is None:
            await db.commit()
            logger.info("Duplicate Stripe webhook ignored: %s", result.event_id)
            return Response(status_code=200)

    if result.event_type == "checkout.session.completed" and result.user_id:
        stmt = select(User).where(User.id == result.user_id)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if user:
            before_tier = user.tier.value
            tier_map = {"basic": UserTier.BASIC, "pro": UserTier.PRO}
            user.tier = tier_map.get(result.tier or "", user.tier)
            user.stripe_customer_id = result.customer_id
            user.stripe_subscription_id = result.subscription_id
            # Plan 8 T5: only bump on an actual transition (skip no-op re-deliveries
            # that survive idempotency, e.g. manual replays after admin tier reset).
            if user.tier.value != before_tier:
                TIER_UPGRADE_TOTAL.labels(
                    from_tier=before_tier,
                    to_tier=user.tier.value,
                    source="webhook",
                ).inc()
            # Plan 7 T1: audit tier upgrade (webhook-driven)
            await log_audit_event(
                db,
                action="tier_upgrade",
                actor_type="webhook",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                before_state={"tier": before_tier},
                after_state={
                    "tier": user.tier.value,
                    "subscription_id": result.subscription_id,
                },
                metadata={"event_id": result.event_id},
            )
            await db.commit()

    elif result.event_type == "customer.subscription.deleted" and result.subscription_id:
        stmt = select(User).where(User.stripe_subscription_id == result.subscription_id)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if user:
            before_tier = user.tier.value
            user.tier = UserTier.FREE
            user.stripe_subscription_id = None
            # Plan 8 T5: only bump when the user actually held a paid tier before;
            # otherwise the deleted event is a no-op transition.
            if before_tier != UserTier.FREE.value:
                TIER_DOWNGRADE_TOTAL.labels(
                    from_tier=before_tier,
                    to_tier=UserTier.FREE.value,
                    reason="subscription_deleted",
                ).inc()
            # Plan 7 T1: audit tier downgrade (webhook-driven)
            await log_audit_event(
                db,
                action="tier_downgrade",
                actor_type="webhook",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                before_state={"tier": before_tier},
                after_state={"tier": UserTier.FREE.value},
                metadata={"event_id": result.event_id},
            )
            await db.commit()

    elif result.event_type == "invoice.payment_failed":
        # Soft suspend: log only. Lifecycle end is handled when Stripe later
        # fires customer.subscription.deleted (after retry exhaustion).
        logger.warning(
            "Stripe invoice.payment_failed: subscription=%s customer=%s action=%s",
            result.subscription_id,
            result.customer_id,
            result.action,
        )

    # Always commit (covers idempotency insert) and ack 200 to Stripe.
    await db.commit()
    return Response(status_code=200)


@router.delete("/subscription", status_code=204)
async def cancel_subscription(
    current_user: CurrentUser,
    db: DbSession,
    stripe_svc: StripeServiceDep,
) -> None:
    """Schedule cancellation at period end. The user keeps tier access until
    Stripe fires ``customer.subscription.deleted``; only then do we downgrade.
    """
    if not current_user.stripe_subscription_id:
        raise HTTPException(status_code=404, detail="No active subscription")
    stripe_svc.cancel_subscription(current_user.stripe_subscription_id)
    # Plan 7 T1: audit user-initiated subscription cancel
    await log_audit_event(
        db,
        action="subscription_cancel",
        user_id=current_user.id,
        resource_type="subscription",
        resource_id=current_user.stripe_subscription_id,
        metadata={"stripe_subscription_id": current_user.stripe_subscription_id},
    )
    await db.commit()
    # Intentionally do NOT mutate tier / clear subscription_id here.


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(current_user: CurrentUser) -> BillingStatusResponse:
    expires = (
        current_user.subscription_expires_at.isoformat()
        if current_user.subscription_expires_at
        else None
    )
    return BillingStatusResponse(
        tier=current_user.tier,
        stripe_customer_id=current_user.stripe_customer_id,
        stripe_subscription_id=current_user.stripe_subscription_id,
        subscription_expires_at=expires,
    )
