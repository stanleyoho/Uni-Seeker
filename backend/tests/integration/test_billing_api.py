from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User


async def _create_user(
    db: AsyncSession,
    email: str = "pay@example.com",
    tier: UserTier = UserTier.FREE,
) -> User:
    user = User(email=email, hashed_password="x" * 60, username=email.split("@")[0])
    user.tier = tier
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
@patch("app.api.v1.billing.get_stripe_service")
async def test_create_checkout_session(
    mock_svc_dep: MagicMock, client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_user(db_session)
    token = create_access_token(user.id, user.email)

    mock_svc = MagicMock()
    mock_svc.create_checkout_session.return_value = "https://checkout.stripe.com/pay/cs_test_abc"
    mock_svc_dep.return_value = mock_svc

    response = await client.post(
        "/api/v1/billing/checkout",
        json={"tier": "basic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_abc"


@pytest.mark.asyncio
async def test_billing_status_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/billing/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_billing_status_authenticated(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session, email="status@example.com", tier=UserTier.BASIC)
    token = create_access_token(user.id, user.email)

    response = await client.get(
        "/api/v1/billing/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "basic"


@pytest.mark.asyncio
@patch("app.api.v1.billing.get_stripe_service")
async def test_webhook_idempotent_duplicate_event_ignored(
    mock_svc_dep: MagicMock, client: AsyncClient, db_session: AsyncSession
) -> None:
    """同一 Stripe event 重送，副作用只能執行一次（user.tier 不會被覆蓋兩次）。"""
    from app.modules.billing.stripe_service import WebhookResult

    user = await _create_user(db_session, email="idem@example.com", tier=UserTier.FREE)

    mock_svc = MagicMock()
    mock_svc.handle_webhook.return_value = WebhookResult(
        event_type="checkout.session.completed",
        event_id="evt_idempotent_123",
        user_id=user.id,
        tier="basic",
        subscription_id="sub_x",
        customer_id="cus_x",
    )
    mock_svc_dep.return_value = mock_svc

    # 第一次：應升級為 BASIC
    r1 = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert r1.status_code == 200

    await db_session.refresh(user)
    assert user.tier == UserTier.BASIC

    # 模擬 admin 將 tier 手動降回 FREE，確認重送 webhook 不會再次升級
    user.tier = UserTier.FREE
    await db_session.commit()

    # 第二次：相同 event_id，必須被去重，user.tier 維持 FREE
    r2 = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert r2.status_code == 200

    await db_session.refresh(user)
    assert user.tier == UserTier.FREE, "Duplicate webhook must not re-apply side effect"


@pytest.mark.asyncio
@patch("app.api.v1.billing.get_stripe_service")
async def test_webhook_upgrade_increments_counter(
    mock_svc_dep: MagicMock, client: AsyncClient, db_session: AsyncSession
) -> None:
    """Plan 8 T5: a free→pro checkout.session.completed must bump
    uni_tier_upgrade_total{from_tier="free",to_tier="pro",source="webhook"}."""
    from app.modules.billing.stripe_service import WebhookResult
    from app.obs.metrics import TIER_UPGRADE_TOTAL

    user = await _create_user(db_session, email="upgrade@example.com", tier=UserTier.FREE)

    before = TIER_UPGRADE_TOTAL.labels(
        from_tier="free", to_tier="pro", source="webhook"
    )._value.get()

    mock_svc = MagicMock()
    mock_svc.handle_webhook.return_value = WebhookResult(
        event_type="checkout.session.completed",
        event_id="evt_upgrade_pro_1",
        user_id=user.id,
        tier="pro",
        subscription_id="sub_upgrade",
        customer_id="cus_upgrade",
    )
    mock_svc_dep.return_value = mock_svc

    response = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 200

    await db_session.refresh(user)
    assert user.tier == UserTier.PRO

    after = TIER_UPGRADE_TOTAL.labels(
        from_tier="free", to_tier="pro", source="webhook"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
@patch("app.api.v1.billing.get_stripe_service")
async def test_webhook_downgrade_increments_counter(
    mock_svc_dep: MagicMock, client: AsyncClient, db_session: AsyncSession
) -> None:
    """Plan 8 T5: customer.subscription.deleted on a paid user must bump
    uni_tier_downgrade_total{from_tier="pro",to_tier="free",reason="subscription_deleted"}."""
    from app.modules.billing.stripe_service import WebhookResult
    from app.obs.metrics import TIER_DOWNGRADE_TOTAL

    user = await _create_user(db_session, email="downgrade@example.com", tier=UserTier.PRO)
    user.stripe_subscription_id = "sub_downgrade"
    await db_session.commit()

    before = TIER_DOWNGRADE_TOTAL.labels(
        from_tier="pro", to_tier="free", reason="subscription_deleted"
    )._value.get()

    mock_svc = MagicMock()
    mock_svc.handle_webhook.return_value = WebhookResult(
        event_type="customer.subscription.deleted",
        event_id="evt_downgrade_pro_1",
        subscription_id="sub_downgrade",
        customer_id="cus_downgrade",
    )
    mock_svc_dep.return_value = mock_svc

    response = await client.post(
        "/api/v1/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert response.status_code == 200

    await db_session.refresh(user)
    assert user.tier == UserTier.FREE

    after = TIER_DOWNGRADE_TOTAL.labels(
        from_tier="pro", to_tier="free", reason="subscription_deleted"
    )._value.get()
    assert after == before + 1
