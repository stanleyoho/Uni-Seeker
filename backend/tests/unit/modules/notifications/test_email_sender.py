"""Unit tests for email_sender.send_email.

Boundary contract — given a stubbed ``smtplib.SMTP`` we verify the
function returns the right boolean, builds the right MIME message,
and never raises into the caller. No real SMTP connection is made.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.modules.notifications.email_sender import send_email


def _mk_settings(**overrides) -> Settings:
    """Spin up a Settings instance with SMTP filled in by default."""
    defaults = dict(
        uni_smtp_host="smtp.example.com",
        uni_smtp_port=587,
        uni_smtp_user="bot@example.com",
        uni_smtp_password="secret",
        uni_smtp_from_addr="bot@example.com",
        uni_smtp_use_tls=True,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def mock_smtp_class():
    """Patch the SMTP class so each test sees a fresh MagicMock."""
    with patch("app.modules.notifications.email_sender.smtplib.SMTP") as mock_cls:
        instance = MagicMock()
        # Context manager protocol: __enter__ returns the same mock so
        # ``with smtplib.SMTP(...) as smtp: smtp.send_message(...)``
        # records calls on a single object the test can inspect.
        instance.__enter__.return_value = instance
        instance.__exit__.return_value = False
        mock_cls.return_value = instance
        yield mock_cls, instance


async def test_send_email_returns_true_on_success(mock_smtp_class) -> None:
    """Happy path: SMTP send completes → True; STARTTLS + login fired."""
    mock_cls, smtp = mock_smtp_class
    cfg = _mk_settings()

    ok = await send_email(
        to="user@example.com",
        subject="hello",
        body_text="world",
        cfg=cfg,
    )
    assert ok is True

    # Verify SMTP transaction shape — connect, STARTTLS, login, send.
    mock_cls.assert_called_once()
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("bot@example.com", "secret")
    smtp.send_message.assert_called_once()


async def test_send_email_returns_false_on_smtp_exception(
    mock_smtp_class,
) -> None:
    """SMTPException on send → False (no raise into caller)."""
    _mock_cls, smtp = mock_smtp_class
    smtp.send_message.side_effect = smtplib.SMTPException("550 rejected")
    cfg = _mk_settings()

    ok = await send_email(
        to="user@example.com",
        subject="s",
        body_text="b",
        cfg=cfg,
    )
    assert ok is False


async def test_send_email_returns_false_on_connection_error(
    mock_smtp_class,
) -> None:
    """OSError on connect (relay down / DNS) → False, never raises."""
    mock_cls, _smtp = mock_smtp_class
    mock_cls.side_effect = OSError("connection refused")
    cfg = _mk_settings()

    ok = await send_email(
        to="user@example.com",
        subject="s",
        body_text="b",
        cfg=cfg,
    )
    assert ok is False


async def test_send_email_html_alternative_added(mock_smtp_class) -> None:
    """body_html promotes message to multipart/alternative."""
    _mock_cls, smtp = mock_smtp_class
    cfg = _mk_settings()

    ok = await send_email(
        to="user@example.com",
        subject="hello",
        body_text="plain",
        body_html="<p>rich</p>",
        cfg=cfg,
    )
    assert ok is True
    # Inspect the EmailMessage handed to send_message.
    (msg,), _ = smtp.send_message.call_args
    assert msg.is_multipart()
    # The HTML alternative is the second-attached part.
    parts = list(msg.iter_parts())
    content_types = {p.get_content_type() for p in parts}
    assert "text/plain" in content_types
    assert "text/html" in content_types


async def test_send_email_disabled_when_no_host() -> None:
    """Missing uni_smtp_host → False, no SMTP class instantiated."""
    cfg = _mk_settings(uni_smtp_host=None)
    with patch("app.modules.notifications.email_sender.smtplib.SMTP") as mock_cls:
        ok = await send_email(
            to="user@example.com",
            subject="s",
            body_text="b",
            cfg=cfg,
        )
    assert ok is False
    mock_cls.assert_not_called()


async def test_send_email_disabled_when_no_from_addr() -> None:
    """Missing uni_smtp_from_addr → False, no SMTP class instantiated."""
    cfg = _mk_settings(uni_smtp_from_addr=None)
    with patch("app.modules.notifications.email_sender.smtplib.SMTP") as mock_cls:
        ok = await send_email(
            to="user@example.com",
            subject="s",
            body_text="b",
            cfg=cfg,
        )
    assert ok is False
    mock_cls.assert_not_called()


async def test_send_email_no_auth_when_creds_missing(
    mock_smtp_class,
) -> None:
    """A relay without creds → send_message still fires, login does NOT."""
    _mock_cls, smtp = mock_smtp_class
    cfg = _mk_settings(uni_smtp_user=None, uni_smtp_password=None)

    ok = await send_email(
        to="user@example.com",
        subject="s",
        body_text="b",
        cfg=cfg,
    )
    assert ok is True
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once()


async def test_send_email_starttls_skipped_when_disabled(
    mock_smtp_class,
) -> None:
    """uni_smtp_use_tls=False → no starttls() call (plain submission)."""
    _mock_cls, smtp = mock_smtp_class
    cfg = _mk_settings(uni_smtp_use_tls=False)

    ok = await send_email(
        to="user@example.com",
        subject="s",
        body_text="b",
        cfg=cfg,
    )
    assert ok is True
    smtp.starttls.assert_not_called()
    smtp.send_message.assert_called_once()


async def test_send_email_empty_recipient_returns_false(
    mock_smtp_class,
) -> None:
    """Empty ``to`` → False without touching the SMTP class."""
    mock_cls, _smtp = mock_smtp_class
    cfg = _mk_settings()

    ok = await send_email(to="", subject="s", body_text="b", cfg=cfg)
    assert ok is False
    mock_cls.assert_not_called()
