from pydantic import BaseModel

from app.models.enums import UserTier


class CheckoutRequest(BaseModel):
    tier: str  # "basic" | "pro"


class CheckoutResponse(BaseModel):
    checkout_url: str


class BillingStatusResponse(BaseModel):
    tier: UserTier
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_expires_at: str | None  # ISO 8601
