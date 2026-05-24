"""Integration tests for /api/v1/me/notifications and the per-filer
preferences endpoint at /api/v1/institutional/filers/{id}/preferences.

Layout (~5 cases):
  - PATCH /me/notifications updates telegram_chat_id
  - PATCH /me/notifications with JSON null clears the column
  - PATCH /filers/{id}/preferences toggles notify_on_new_filing
  - 401 unauthenticated
  - 404 when preferences requested for a filer the user is not
    subscribed to
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.auth import create_access_token
from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.subscription import F13UserSubscription
from app.models.enums import UserTier
from app.models.user import User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


async def _mk_user(
    db: "AsyncSession",
    email: str,
    *,
    chat_id: str | None = None,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=email.split("@")[0],
    )
    u.tier = tier
    u.telegram_chat_id = chat_id
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.email)}"
    }


# ── /me/notifications ───────────────────────────────────────────────────


async def test_get_me_notifications_returns_current_state(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    user = await _mk_user(db_session, "me1@x.com", chat_id="chat-init")
    resp = await client.get(
        "/api/v1/me/notifications", headers=_auth(user)
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "telegram_chat_id": "chat-init",
        "notify_via_email": False,
    }


async def test_patch_me_notifications_sets_telegram_chat_id(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    user = await _mk_user(db_session, "me2@x.com", chat_id=None)
    resp = await client.patch(
        "/api/v1/me/notifications",
        headers=_auth(user),
        json={"telegram_chat_id": "987654"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "telegram_chat_id": "987654",
        "notify_via_email": False,
    }

    fresh = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    assert fresh.scalar_one().telegram_chat_id == "987654"


async def test_patch_me_notifications_clears_telegram_chat_id_with_null(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    user = await _mk_user(db_session, "me3@x.com", chat_id="to-clear")
    resp = await client.patch(
        "/api/v1/me/notifications",
        headers=_auth(user),
        json={"telegram_chat_id": None},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "telegram_chat_id": None,
        "notify_via_email": False,
    }

    fresh = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    assert fresh.scalar_one().telegram_chat_id is None


async def test_patch_me_notifications_toggles_notify_via_email(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    """Round 14: PATCH the email opt-in independently of TG chat id."""
    user = await _mk_user(db_session, "em1@x.com", chat_id="keep-me")
    resp = await client.patch(
        "/api/v1/me/notifications",
        headers=_auth(user),
        json={"notify_via_email": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notify_via_email"] is True
    # PATCH was partial — telegram_chat_id stayed put.
    assert body["telegram_chat_id"] == "keep-me"

    fresh = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    row = fresh.scalar_one()
    assert row.notify_via_email is True
    assert row.telegram_chat_id == "keep-me"


async def test_patch_me_notifications_401_when_unauthenticated(
    client: "AsyncClient",
) -> None:
    resp = await client.patch(
        "/api/v1/me/notifications",
        json={"telegram_chat_id": "x"},
    )
    assert resp.status_code in (401, 403)


# ── /institutional/filers/{id}/preferences ──────────────────────────────


async def _seed_subscription(
    db: "AsyncSession", user: User, cik: str = "0099000001"
) -> F13UserSubscription:
    filer = F13Filer(cik=cik, name="PrefCo")
    db.add(filer)
    await db.commit()
    await db.refresh(filer)

    sub = F13UserSubscription(user_id=user.id, filer_id=filer.id)
    sub.notify_on_new_filing = True
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def test_patch_filer_preferences_toggles_notify_flag(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    user = await _mk_user(db_session, "pref1@x.com")
    sub = await _seed_subscription(db_session, user)

    resp = await client.patch(
        f"/api/v1/institutional/filers/{sub.filer_id}/preferences",
        headers=_auth(user),
        json={"notify_on_new_filing": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filer_id"] == sub.filer_id
    assert body["notify_on_new_filing"] is False

    fresh = await db_session.execute(
        select(F13UserSubscription).where(F13UserSubscription.id == sub.id)
    )
    assert fresh.scalar_one().notify_on_new_filing is False


async def test_patch_filer_preferences_404_for_non_subscribed_filer(
    client: "AsyncClient", db_session: "AsyncSession"
) -> None:
    user = await _mk_user(db_session, "pref2@x.com")
    # Create a filer but DO NOT subscribe.
    filer = F13Filer(cik="0099000002", name="UnsubCo")
    db_session.add(filer)
    await db_session.commit()
    await db_session.refresh(filer)

    resp = await client.patch(
        f"/api/v1/institutional/filers/{filer.id}/preferences",
        headers=_auth(user),
        json={"notify_on_new_filing": False},
    )
    assert resp.status_code == 404


async def test_patch_filer_preferences_401_when_unauthenticated(
    client: "AsyncClient",
) -> None:
    resp = await client.patch(
        "/api/v1/institutional/filers/1/preferences",
        json={"notify_on_new_filing": False},
    )
    assert resp.status_code in (401, 403)
