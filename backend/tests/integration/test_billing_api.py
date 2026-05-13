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
async def test_billing_status_authenticated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
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
