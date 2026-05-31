from pydantic import BaseModel

from app.models.enums import UserTier
from app.schemas._base import StrictModel


class CheckoutRequest(StrictModel):
    tier: str  # "basic" | "pro"


class CheckoutResponse(BaseModel):
    checkout_url: str


class BillingStatusResponse(BaseModel):
    tier: UserTier
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_expires_at: str | None  # ISO 8601
