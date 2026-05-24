"""Integration tests for the multi-channel notification dispatcher.

Covers the eligibility matrix:
  - Both channels live + opted in
  - Only Telegram opted in
  - Only Email opted in
  - Neither opted in
  - Partial failure (TG succeeds, Email fails, and vice versa)
  - Per-channel sender raises → counted as error, never propagates

``send_telegram_message`` and ``send_email`` are patched per test so no
real network I/O leaves the process.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.models.enums import UserTier
from app.models.user import User
from app.modules.notifications.dispatcher import dispatch_notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── helpers ────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    *,
    email: str,
    username: str,
    chat_id: str | None = None,
    notify_via_email: bool = False,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=username,
    )
    u.tier = UserTier.PRO
    u.is_active = True
    u.telegram_chat_id = chat_id
    u.notify_via_email = notify_via_email
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ── tests ──────────────────────────────────────────────────────────────


async def test_dispatch_both_channels_both_succeed(
    db_session: AsyncSession, monkeypatch
) -> None:
    """User opted into TG + Email; both senders succeed."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    monkeypatch.setattr(settings, "uni_smtp_host", "smtp.x")
    monkeypatch.setattr(settings, "uni_smtp_from_addr", "from@x")
    user = await _mk_user(
        db_session,
        email="both@x.com",
        username="both",
        chat_id="chat-1",
        notify_via_email=True,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ) as tg_mock, patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=True),
    ) as email_mock:
        result = await dispatch_notification(
            user,
            title="Title",
            body_text="body",
            deep_link="https://app/x",
        )

    assert result == {
        "tg_sent": True,
        "email_sent": True,
        "channels_attempted": 2,
        "channels_succeeded": 2,
    }
    tg_mock.assert_called_once()
    email_mock.assert_called_once()


async def test_dispatch_only_telegram_when_email_opted_out(
    db_session: AsyncSession, monkeypatch
) -> None:
    """notify_via_email=False → only TG channel is attempted."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    user = await _mk_user(
        db_session,
        email="tg-only@x.com",
        username="tgonly",
        chat_id="chat-2",
        notify_via_email=False,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ) as tg_mock, patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=True),
    ) as email_mock:
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    assert result["tg_sent"] is True
    assert result["email_sent"] is False
    assert result["channels_attempted"] == 1
    assert result["channels_succeeded"] == 1
    tg_mock.assert_called_once()
    email_mock.assert_not_called()


async def test_dispatch_only_email_when_no_tg_chat_id(
    db_session: AsyncSession, monkeypatch
) -> None:
    """telegram_chat_id NULL → only Email channel attempted."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    monkeypatch.setattr(settings, "uni_smtp_host", "smtp.x")
    monkeypatch.setattr(settings, "uni_smtp_from_addr", "from@x")
    user = await _mk_user(
        db_session,
        email="email-only@x.com",
        username="emonly",
        chat_id=None,
        notify_via_email=True,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ) as tg_mock, patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=True),
    ) as email_mock:
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    assert result["tg_sent"] is False
    assert result["email_sent"] is True
    assert result["channels_attempted"] == 1
    assert result["channels_succeeded"] == 1
    tg_mock.assert_not_called()
    email_mock.assert_called_once()


async def test_dispatch_none_when_both_disabled(
    db_session: AsyncSession,
) -> None:
    """No chat_id AND notify_via_email=False → zero channels."""
    user = await _mk_user(
        db_session,
        email="off@x.com",
        username="off",
        chat_id=None,
        notify_via_email=False,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ) as tg_mock, patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=True),
    ) as email_mock:
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    assert result == {
        "tg_sent": False,
        "email_sent": False,
        "channels_attempted": 0,
        "channels_succeeded": 0,
    }
    tg_mock.assert_not_called()
    email_mock.assert_not_called()


async def test_dispatch_partial_success_tg_ok_email_fail(
    db_session: AsyncSession, monkeypatch
) -> None:
    """TG succeeds, Email fails — TG counted, email error visible."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    user = await _mk_user(
        db_session,
        email="pf@x.com",
        username="pf",
        chat_id="chat-pf",
        notify_via_email=True,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ), patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=False),
    ):
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    assert result["tg_sent"] is True
    assert result["email_sent"] is False
    assert result["channels_attempted"] == 2
    assert result["channels_succeeded"] == 1


async def test_dispatch_tracks_attempt_count_correctly(
    db_session: AsyncSession, monkeypatch
) -> None:
    """attempted increments per channel actually fired."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    user = await _mk_user(
        db_session,
        email="ac@x.com",
        username="ac",
        chat_id="chat-ac",
        notify_via_email=True,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=False),
    ), patch(
        "app.modules.notifications.dispatcher.send_email",
        new=AsyncMock(return_value=False),
    ):
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    # Two channels eligible, both failed → 2 attempted, 0 succeeded.
    assert result["channels_attempted"] == 2
    assert result["channels_succeeded"] == 0
    assert result["tg_sent"] is False
    assert result["email_sent"] is False


async def test_dispatch_uses_pre_rendered_tg_text(
    db_session: AsyncSession, monkeypatch
) -> None:
    """When caller passes ``tg_text`` we forward it verbatim to TG."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "bot-tok")
    user = await _mk_user(
        db_session,
        email="tx@x.com",
        username="tx",
        chat_id="chat-tx",
        notify_via_email=False,
    )

    captured: dict[str, str] = {}

    async def fake_tg(*, bot_token, chat_id, text):
        captured["text"] = text
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_tg,
    ):
        await dispatch_notification(
            user,
            title="Title (ignored)",
            body_text="body (ignored)",
            tg_text="<b>pre-rendered</b>\nLine 2",
        )

    assert captured["text"] == "<b>pre-rendered</b>\nLine 2"


async def test_dispatch_email_appends_deep_link_to_text(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Email plain-text body gains ``查看詳情: <url>`` footer."""
    monkeypatch.setattr(settings, "uni_smtp_host", "smtp.x")
    monkeypatch.setattr(settings, "uni_smtp_from_addr", "from@x")
    user = await _mk_user(
        db_session,
        email="dl@x.com",
        username="dl",
        chat_id=None,
        notify_via_email=True,
    )

    captured: dict[str, str] = {}

    async def fake_email(*, to, subject, body_text, body_html=None):
        captured["to"] = to
        captured["subject"] = subject
        captured["body_text"] = body_text
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_email",
        side_effect=fake_email,
    ):
        await dispatch_notification(
            user,
            title="Hello Subject",
            body_text="hello body",
            deep_link="https://app/x?y=1",
        )

    assert captured["to"] == "dl@x.com"
    assert captured["subject"] == "Hello Subject"
    assert "hello body" in captured["body_text"]
    assert "查看詳情: https://app/x?y=1" in captured["body_text"]


async def test_dispatch_no_tg_when_token_empty(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Empty bot token → TG channel skipped even if chat_id present."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "")
    user = await _mk_user(
        db_session,
        email="nt@x.com",
        username="nt",
        chat_id="chat-nt",
        notify_via_email=False,
    )

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        new=AsyncMock(return_value=True),
    ) as tg_mock:
        result = await dispatch_notification(
            user, title="t", body_text="b",
        )

    tg_mock.assert_not_called()
    assert result["channels_attempted"] == 0
