import json
from unittest.mock import MagicMock, patch

import pytest

from app.modules.billing.stripe_service import StripeService, WebhookResult


def _make_event(event_type: str, data: dict) -> bytes:
    """Build a minimal Stripe event JSON payload."""
    return json.dumps({"type": event_type, "data": {"object": data}}).encode()


@pytest.fixture
def price_ids() -> dict[str, str]:
    return {
        "basic": "price_basic_monthly_twd299",
        "pro": "price_pro_monthly_twd899",
    }


@pytest.fixture
def service(price_ids: dict[str, str]) -> StripeService:
    return StripeService(
        secret_key="sk_test_fake",
        webhook_secret="whsec_fake",
        price_ids=price_ids,
    )


def test_price_ids_injected(service: StripeService, price_ids: dict[str, str]):
    """price_ids 必須從建構式注入，而非寫死在類別。"""
    assert service._price_ids == price_ids
    assert "basic" in service._price_ids
    assert "pro" in service._price_ids


@patch("stripe.checkout.Session.create")
def test_create_checkout_session_returns_url(mock_create: MagicMock, service: StripeService):
    mock_create.return_value = MagicMock(url="https://checkout.stripe.com/pay/cs_test_abc123")
    url = service.create_checkout_session(
        user_id=42,
        tier="basic",
        success_url="https://app.local/success",
        cancel_url="https://app.local/cancel",
    )
    assert url == "https://checkout.stripe.com/pay/cs_test_abc123"
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["mode"] == "subscription"
    assert call_kwargs["line_items"][0]["price"] == service._price_ids["basic"]
    assert call_kwargs["metadata"]["user_id"] == "42"


@patch("stripe.checkout.Session.create")
def test_create_checkout_session_invalid_tier(mock_create: MagicMock, service: StripeService):
    with pytest.raises(ValueError, match="Invalid tier"):
        service.create_checkout_session(
            user_id=1,
            tier="free",  # free 沒有 price_id
            success_url="https://app.local/success",
            cancel_url="https://app.local/cancel",
        )


@patch("stripe.Webhook.construct_event")
def test_webhook_checkout_completed(mock_construct: MagicMock, service: StripeService):
    payload = _make_event(
        "checkout.session.completed",
        {
            "metadata": {"user_id": "99", "tier": "pro"},
            "subscription": "sub_abc",
            "customer": "cus_xyz",
        },
    )
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"user_id": "99", "tier": "pro"},
                "subscription": "sub_abc",
                "customer": "cus_xyz",
            }
        },
    }

    result = service.handle_webhook(payload, signature="t=1,v1=fakesig")
    assert result.event_type == "checkout.session.completed"
    assert result.user_id == 99
    assert result.tier == "pro"
    assert result.subscription_id == "sub_abc"
    assert result.customer_id == "cus_xyz"


@patch("stripe.Webhook.construct_event")
def test_webhook_subscription_deleted(mock_construct: MagicMock, service: StripeService):
    mock_construct.return_value = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_abc",
                "customer": "cus_xyz",
                "metadata": {},
            }
        },
    }
    result = service.handle_webhook(b"{}", signature="t=1,v1=fakesig")
    assert result.event_type == "customer.subscription.deleted"
    assert result.subscription_id == "sub_abc"
    assert result.customer_id == "cus_xyz"


@patch("stripe.Webhook.construct_event")
def test_webhook_invoice_payment_failed(mock_construct: MagicMock, service: StripeService):
    """invoice.payment_failed 必須回傳 action='downgrade_pending'，作為軟暫停訊號。"""
    mock_construct.return_value = {
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "subscription": "sub_abc",
                "customer": "cus_xyz",
            }
        },
    }
    result = service.handle_webhook(b"{}", signature="t=1,v1=fakesig")
    assert result.event_type == "invoice.payment_failed"
    assert result.subscription_id == "sub_abc"
    assert result.customer_id == "cus_xyz"
    assert result.action == "downgrade_pending"


@patch("stripe.Webhook.construct_event")
def test_webhook_invalid_signature_raises(mock_construct: MagicMock, service: StripeService):
    import stripe as stripe_lib

    mock_construct.side_effect = stripe_lib.error.SignatureVerificationError(
        "Invalid signature", sig_header="bad"
    )
    with pytest.raises(ValueError, match="Invalid webhook signature"):
        service.handle_webhook(b"{}", signature="bad")


@patch("stripe.Subscription.modify")
def test_cancel_subscription_uses_period_end(mock_modify: MagicMock, service: StripeService):
    """cancel_subscription 必須呼叫 Subscription.modify 並帶 cancel_at_period_end=True，
    而非立即 delete。"""
    service.cancel_subscription("sub_abc")
    mock_modify.assert_called_once_with("sub_abc", cancel_at_period_end=True)
