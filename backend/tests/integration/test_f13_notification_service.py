"""Integration tests for F13NotificationService.

Covers the fan-out contract:
  - eligible recipients receive a TG message
  - skip rules (no chat_id / opted out / inactive) are respected
  - cross-user isolation
  - empty new_filings is a no-op
  - partial send failures are counted, not raised
  - audit row is written

``send_telegram_message`` is patched per-test to a thin coroutine so
NO real HTTP call ever leaves the test process.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

from sqlalchemy import func, select

from app.config import settings
from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.filing import F13Filing
from app.db.models.institutional.subscription import F13UserSubscription
from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User
from app.services.institutional.notification_service import (
    F13NotificationService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── helpers ────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    *,
    email: str,
    username: str,
    chat_id: str | None,
    tier: UserTier = UserTier.PRO,
    is_active: bool = True,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=username,
    )
    u.tier = tier
    u.is_active = is_active
    u.telegram_chat_id = chat_id
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_filer(db: AsyncSession, *, cik: str, name: str) -> F13Filer:
    f = F13Filer(cik=cik, name=name)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


async def _mk_subscription(
    db: AsyncSession,
    *,
    user_id: int,
    filer_id: int,
    notify: bool = True,
) -> F13UserSubscription:
    sub = F13UserSubscription(user_id=user_id, filer_id=filer_id)
    sub.notify_on_new_filing = notify
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def _mk_filing(
    db: AsyncSession,
    *,
    filer_id: int,
    accession: str,
    period: date = date(2025, 12, 31),
) -> F13Filing:
    f = F13Filing(
        filer_id=filer_id,
        accession_number=accession,
        form_type="13F-HR",
        report_period_end=period,
        filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
    )
    f.total_value_usd = Decimal("1234567")
    f.total_positions = 42
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


# ── tests ──────────────────────────────────────────────────────────────


async def test_notify_new_filings_sends_to_subscribed_users(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake-token")

    user = await _mk_user(
        db_session,
        email="n1@x.com",
        username="n1",
        chat_id="chat-1",
    )
    filer = await _mk_filer(db_session, cik="0010000001", name="ACME Capital")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-1"
    )

    calls: list[dict] = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result == {
        "notified": 1,
        "skipped_no_chat_id": 0,
        "skipped_opted_out": 0,
        "errors": 0,
        "tg_sent": 1,
        "email_sent": 0,
    }
    assert len(calls) == 1
    assert calls[0]["chat_id"] == "chat-1"
    assert calls[0]["bot_token"] == "fake-token"
    assert "ACME Capital" in calls[0]["text"]
    assert "13F" in calls[0]["text"]


async def test_notify_skips_users_without_telegram_chat_id(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user = await _mk_user(
        db_session, email="n2@x.com", username="n2", chat_id=None
    )
    filer = await _mk_filer(db_session, cik="0010000002", name="NoChat Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-2"
    )

    async def fake_send(**kwargs):  # pragma: no cover - must NOT be called
        raise AssertionError("should not send when chat_id is NULL")

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result["notified"] == 0
    assert result["skipped_no_chat_id"] == 1
    assert result["errors"] == 0


async def test_notify_respects_notify_on_new_filing_false(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user = await _mk_user(
        db_session,
        email="n3@x.com",
        username="n3",
        chat_id="chat-3",
    )
    filer = await _mk_filer(db_session, cik="0010000003", name="Opted Out Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=False
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-3"
    )

    async def fake_send(**kwargs):  # pragma: no cover - must NOT fire
        raise AssertionError("must not send when notify_on_new_filing is False")

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result["notified"] == 0
    assert result["skipped_opted_out"] == 1


async def test_notify_handles_partial_send_failures(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user_a = await _mk_user(
        db_session, email="na@x.com", username="na", chat_id="chat-a"
    )
    user_b = await _mk_user(
        db_session, email="nb@x.com", username="nb", chat_id="chat-b"
    )
    filer = await _mk_filer(db_session, cik="0010000004", name="Partial Co")
    await _mk_subscription(
        db_session, user_id=user_a.id, filer_id=filer.id, notify=True
    )
    await _mk_subscription(
        db_session, user_id=user_b.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-4"
    )

    async def fake_send(**kwargs):
        return kwargs["chat_id"] == "chat-a"

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result["notified"] == 1
    assert result["errors"] == 1


async def test_notify_cross_user_isolation(
    db_session: AsyncSession, monkeypatch
) -> None:
    """User subscribed to filer X must NOT receive alerts for filer Y."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user_x = await _mk_user(
        db_session, email="ix@x.com", username="ix", chat_id="chat-x"
    )
    user_y = await _mk_user(
        db_session, email="iy@x.com", username="iy", chat_id="chat-y"
    )
    filer_x = await _mk_filer(db_session, cik="0010000005", name="X Corp")
    filer_y = await _mk_filer(db_session, cik="0010000006", name="Y Corp")
    await _mk_subscription(
        db_session, user_id=user_x.id, filer_id=filer_x.id, notify=True
    )
    await _mk_subscription(
        db_session, user_id=user_y.id, filer_id=filer_y.id, notify=True
    )
    filing_x = await _mk_filing(
        db_session, filer_id=filer_x.id, accession="acc-x"
    )

    seen: list[str] = []

    async def fake_send(**kwargs):
        seen.append(kwargs["chat_id"])
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        await svc.notify_new_filings(filer_x.id, [filing_x])
        await db_session.commit()

    assert seen == ["chat-x"]


async def test_notify_handles_empty_new_filings_is_noop(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user = await _mk_user(
        db_session, email="ne@x.com", username="ne", chat_id="chat-e"
    )
    filer = await _mk_filer(db_session, cik="0010000007", name="Empty Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )

    async def fake_send(**kwargs):  # pragma: no cover - must not run
        raise AssertionError("empty new_filings should not call send")

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [])

    assert result == {
        "notified": 0,
        "skipped_no_chat_id": 0,
        "skipped_opted_out": 0,
        "errors": 0,
        "tg_sent": 0,
        "email_sent": 0,
    }


async def test_notify_message_format_contains_filer_and_filing_fields(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")
    monkeypatch.setattr(settings, "app_url", "https://example.test")

    user = await _mk_user(
        db_session, email="fm@x.com", username="fm", chat_id="chat-fm"
    )
    filer = await _mk_filer(
        db_session, cik="0010000008", name="Format Capital"
    )
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-fmt"
    )

    captured: dict[str, str] = {}

    async def fake_send(**kwargs):
        captured["text"] = kwargs["text"]
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        await svc.notify_new_filings(filer.id, [filing])

    text = captured["text"]
    assert "<b>Format Capital</b>" in text
    assert "2025-12-31" in text
    assert "13F-HR" in text
    assert "$1,234,567" in text
    assert "42" in text  # total_positions
    assert f"https://example.test/institutional?filer={filer.id}" in text


async def test_notify_audit_log_written(
    db_session: AsyncSession, monkeypatch
) -> None:
    """A single audit row records the fan-out summary."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user = await _mk_user(
        db_session, email="al@x.com", username="al", chat_id="chat-al"
    )
    filer = await _mk_filer(db_session, cik="0010000009", name="Audit Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-al"
    )

    async def fake_send(**kwargs):
        return True

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    count = await db_session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "f13_notifications_sent",
            AuditLog.resource_id == str(filer.id),
        )
    )
    assert int(count.scalar() or 0) == 1


async def test_notify_disabled_when_token_empty(
    db_session: AsyncSession, monkeypatch
) -> None:
    """uni_telegram_bot_token empty → globally disabled audit row, no sends."""
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "")

    user = await _mk_user(
        db_session, email="dis@x.com", username="dis", chat_id="chat-d"
    )
    filer = await _mk_filer(db_session, cik="0010000010", name="Disabled Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-d"
    )

    async def fake_send(**kwargs):  # pragma: no cover - must not run
        raise AssertionError("must not send when bot_token empty")

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result == {
        "notified": 0,
        "skipped_no_chat_id": 0,
        "skipped_opted_out": 0,
        "errors": 0,
        "tg_sent": 0,
        "email_sent": 0,
    }
    count = await db_session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "f13_notify_skipped_disabled",
        )
    )
    assert int(count.scalar() or 0) == 1


async def test_notify_skips_inactive_users(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "uni_telegram_bot_token", "fake")

    user = await _mk_user(
        db_session,
        email="inact@x.com",
        username="inact",
        chat_id="chat-i",
        is_active=False,
    )
    filer = await _mk_filer(db_session, cik="0010000011", name="Inactive Co")
    await _mk_subscription(
        db_session, user_id=user.id, filer_id=filer.id, notify=True
    )
    filing = await _mk_filing(
        db_session, filer_id=filer.id, accession="acc-i"
    )

    async def fake_send(**kwargs):  # pragma: no cover - must not run
        raise AssertionError("inactive users must not receive alerts")

    with patch(
        "app.modules.notifications.dispatcher.send_telegram_message",
        side_effect=fake_send,
    ):
        svc = F13NotificationService(db_session)
        result = await svc.notify_new_filings(filer.id, [filing])
        await db_session.commit()

    assert result["notified"] == 0
