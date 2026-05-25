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
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {list(self._price_ids)}")

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user_id), "tier": tier},
        )
        return session.url  # type: ignore[return-value]

    def handle_webhook(self, payload: bytes, signature: str) -> WebhookResult:
        """處理 Stripe webhook 事件，驗證簽名並解析關鍵欄位。"""
        try:
            event = stripe.Webhook.construct_event(payload, signature, self._webhook_secret)  # type: ignore[no-untyped-call]
        except stripe.error.SignatureVerificationError as exc:
            raise ValueError("Invalid webhook signature") from exc

        event_type: str = event["type"]
        event_id: str | None = event.get("id")
        obj = event["data"]["object"]

        if event_type == "checkout.session.completed":
            meta = obj.get("metadata", {})
            return WebhookResult(
                event_type=event_type,
                event_id=event_id,
                user_id=int(meta["user_id"]) if meta.get("user_id") else None,
                tier=meta.get("tier"),
                subscription_id=obj.get("subscription"),
                customer_id=obj.get("customer"),
            )

        if event_type == "customer.subscription.deleted":
            return WebhookResult(
                event_type=event_type,
                event_id=event_id,
                subscription_id=obj.get("id"),
                customer_id=obj.get("customer"),
            )

        if event_type == "invoice.payment_failed":
            # 軟暫停：標記 action 讓 router 記錄/通知，不立即降級
            return WebhookResult(
                event_type=event_type,
                event_id=event_id,
                subscription_id=obj.get("subscription"),
                customer_id=obj.get("customer"),
                action="downgrade_pending",
            )

        # 其他事件忽略，回傳 event_type 供 caller 記錄
        return WebhookResult(event_type=event_type, event_id=event_id)

    def cancel_subscription(self, subscription_id: str) -> None:
        """於計費週期結束時取消訂閱（用戶仍可享用服務至期末）。"""
        stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
