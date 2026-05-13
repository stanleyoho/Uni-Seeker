from __future__ import annotations

from dataclasses import dataclass

import stripe


@dataclass
class WebhookResult:
    event_type: str
    event_id: str | None = None  # Stripe event["id"]，用於 idempotency 去重
    user_id: int | None = None
    tier: str | None = None
    subscription_id: str | None = None
    customer_id: str | None = None
    action: str | None = None  # 例如 "downgrade_pending"（payment_failed 軟暫停）


class StripeService:
    def __init__(
        self,
        secret_key: str,
        webhook_secret: str,
        price_ids: dict[str, str],
    ) -> None:
        """price_ids 由 dependency provider 從 settings 注入，避免硬編碼。"""
        self._webhook_secret = webhook_secret
        self._price_ids = price_ids
        stripe.api_key = secret_key

    def create_checkout_session(
        self,
        user_id: int,
        tier: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """建立 Stripe Checkout Session，返回 checkout URL。"""
        price_id = self._price_ids.get(tier)
        if not price_id:
            raise ValueError(
                f"Invalid tier '{tier}'. Must be one of: {list(self._price_ids)}"
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user_id), "tier": tier},
        )
        return session.url  # type: ignore[return-value]
