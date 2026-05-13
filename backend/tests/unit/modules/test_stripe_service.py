from unittest.mock import MagicMock, patch

import pytest

from app.modules.billing.stripe_service import StripeService, WebhookResult


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
