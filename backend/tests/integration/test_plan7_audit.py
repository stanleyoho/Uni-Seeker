"""Plan 7 T1 — audit_logs entries on Stripe / auth flows."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User


async def _user(
    db: AsyncSession,
    email: str = "u@x.tw",
    username: str = "u",
    tier: UserTier = UserTier.FREE,
    sub_id: str | None = None,
) -> User:
    u = User(
        email=email,
        hashed_password=hash_password("Password123"),
        username=username,
    )
    u.tier = tier
    if sub_id:
        u.stripe_subscription_id = sub_id
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _count(db: AsyncSession, action: str) -> int:
    return (
        await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
        or 0
    )


@pytest.mark.asyncio
async def test_register_writes_audit(client: AsyncClient, db_session: AsyncSession) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@x.tw",
            "password": "Password123",
            "username": "newuser",
        },
    )
    assert r.status_code == 201, r.text
    count = await _count(db_session, "user_register")
    assert count == 1


@pytest.mark.asyncio
async def test_login_writes_audit(client: AsyncClient, db_session: AsyncSession) -> None:
    await _user(db_session, "login@x.tw", "login")
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@x.tw", "password": "Password123"},
    )
    assert r.status_code == 200, r.text
    count = await _count(db_session, "user_login")
    assert count == 1


@pytest.mark.asyncio
async def test_subscription_cancel_writes_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    u = await _user(db_session, "cancel@x.tw", "cancel", tier=UserTier.PRO, sub_id="sub_test")
    token = create_access_token(u.id, u.email)

    mock_svc = MagicMock()
    mock_svc.cancel_subscription.return_value = None
    with patch("app.api.v1.billing.get_stripe_service", return_value=mock_svc):
        r = await client.delete(
            "/api/v1/billing/subscription",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 204, r.text
    count = await _count(db_session, "subscription_cancel")
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.pg_integration
async def test_webhook_tier_upgrade_writes_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """checkout.session.completed -> tier_upgrade audit (actor=webhook)."""
    from app.modules.billing.stripe_service import WebhookResult

    user = await _user(db_session, "upgrade@x.tw", "upgrade", tier=UserTier.FREE)

    mock_svc = MagicMock()
    mock_svc.handle_webhook.return_value = WebhookResult(
        event_type="checkout.session.completed",
        event_id="evt_upgrade_1",
        user_id=user.id,
        tier="pro",
        subscription_id="sub_upgrade",
        customer_id="cus_x",
    )
    with patch("app.api.v1.billing.get_stripe_service", return_value=mock_svc):
        r = await client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=fake"},
        )
    assert r.status_code == 200, r.text

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "tier_upgrade")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_type == "webhook"
    assert row.user_id == user.id
    assert row.before_state == {"tier": "free"}
    assert row.after_state == {"tier": "pro", "subscription_id": "sub_upgrade"}
    assert (row.event_metadata or {}).get("event_id") == "evt_upgrade_1"


@pytest.mark.asyncio
async def test_webhook_tier_downgrade_writes_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """customer.subscription.deleted -> tier_downgrade audit (actor=webhook)."""
    from app.modules.billing.stripe_service import WebhookResult

    user = await _user(
        db_session,
        "downgrade@x.tw",
        "downgrade",
        tier=UserTier.PRO,
        sub_id="sub_dn",
    )

    mock_svc = MagicMock()
    mock_svc.handle_webhook.return_value = WebhookResult(
        event_type="customer.subscription.deleted",
        event_id="evt_downgrade_1",
        subscription_id="sub_dn",
        customer_id="cus_x",
    )
    with patch("app.api.v1.billing.get_stripe_service", return_value=mock_svc):
        r = await client.post(
            "/api/v1/billing/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=fake"},
        )
    assert r.status_code == 200, r.text

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "tier_downgrade")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_type == "webhook"
    assert row.user_id == user.id
    assert row.before_state == {"tier": "pro"}
    assert row.after_state == {"tier": "free"}
    assert (row.event_metadata or {}).get("event_id") == "evt_downgrade_1"
