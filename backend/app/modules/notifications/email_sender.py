"""Email send-only client via stdlib ``smtplib``.

Mirror of ``telegram_sender.py`` for the SMTP channel — fire one
request, log every error path, return a plain ``bool``. The dispatcher
counts a ``False`` return as ``errors`` on the audit row exactly the
same way it counts a failed Telegram send.

Why ``smtplib`` rather than a third-party API client (Resend / SendGrid
/ Postmark)?

  - Zero new dependency. ``smtplib`` ships with CPython.
  - The operator picks the SMTP relay — Gmail, SES, SendGrid SMTP,
    self-hosted Postfix — without touching code.
  - The failure surface is identical to TG (transport, auth, 5xx) and
    callers already handle that boolean contract.

Why ``asyncio.to_thread`` (instead of ``aiosmtplib`` or similar)?

  - ``smtplib`` is sync and would block the event loop on connect /
    handshake / send. Off-loading to the default thread pool keeps the
    refresh / alert loop responsive without paying for another
    dependency. The thread pool is fine for the per-cycle fan-out
    volume we serve (single-digit emails per user per cycle).

Failure semantics:

  - Missing config (``uni_smtp_host`` OR ``uni_smtp_from_addr`` empty)
    → return ``False`` immediately, log at ``warning`` once per call.
  - SMTP transport / auth / send error → return ``False``, log at
    ``warning`` (NOT ``exception`` — these are predictable operational
    failures, not bugs).
  - Any other unexpected exception → caught, logged at ``warning``,
    return ``False``. We never raise into the caller because the
    notification fan-out is best-effort.
"""
from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import Settings, settings as default_settings
from app.obs.logging import get_logger

logger = get_logger(component="email_sender")


# SMTP timeout — be generous enough to survive a slow relay handshake
# but tight enough to not block a refresh cycle. 15s matches the
# operational SLA we already accept for Telegram + a small TLS overhead.
_DEFAULT_TIMEOUT_SECONDS = 15.0


async def send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    cfg: Settings | None = None,
) -> bool:
    """Send a plain (+ optional HTML) email via configured SMTP relay.

    Args:
        to: Recipient address (RFC 5321). Empty string short-circuits
            to ``False`` so a missing ``users.email`` never produces a
            connection.
        subject: ``Subject:`` header — passed straight through. Caller
            is responsible for length (Gmail truncates at ~78 chars).
        body_text: ``text/plain`` body (always included; serves clients
            that disable HTML, and acts as fallback for MIME multipart).
        body_html: Optional ``text/html`` alternative. When set, the
            outgoing message becomes ``multipart/alternative`` and the
            recipient's client picks whichever it prefers.
        timeout: Per-connection timeout in seconds. Applies to connect,
            handshake, and send (one budget for the whole transaction).
        cfg: Override settings (tests pass a Settings instance with the
            SMTP fields filled in). Defaults to the global ``settings``
            singleton so production callers stay one-liners.

    Returns:
        ``True`` on a clean ``smtp.send_message`` return; ``False`` on
        any of: missing config, recipient empty, transport / auth /
        send error.
    """
    cfg = cfg if cfg is not None else default_settings

    # Defensive: an unconfigured deployment must NEVER make an outbound
    # connection. The two required fields are host + from_addr —
    # without those the message cannot leave the relay.
    if not cfg.uni_smtp_host or not cfg.uni_smtp_from_addr:
        logger.warning(
            "email_send_skipped_missing_config",
            has_host=bool(cfg.uni_smtp_host),
            has_from=bool(cfg.uni_smtp_from_addr),
            to=_redact_email(to),
        )
        return False

    if not to:
        # An empty recipient is a programmer error one layer up
        # (dispatcher should have filtered). Log + bail rather than
        # surfacing ``smtplib.SMTPRecipientsRefused``.
        logger.debug("email_send_skipped_empty_recipient")
        return False

    # Build the message OUTSIDE the thread offload so any header
    # composition bug raises in-line (easier to surface in tests) and
    # the worker thread only does the network I/O.
    msg = EmailMessage()
    msg["From"] = cfg.uni_smtp_from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        # EmailMessage promotes itself to multipart/alternative on this
        # call — the plain part stays the fallback for text-only
        # clients, the HTML part renders for everyone else.
        msg.add_alternative(body_html, subtype="html")

    try:
        await asyncio.to_thread(_send_sync, msg, cfg, timeout)
    except (
        smtplib.SMTPException,
        OSError,
        TimeoutError,
    ) as exc:
        # Operational failures — bad creds, relay down, TLS handshake
        # botched. Logged at warning because notifications are
        # best-effort; the audit row counts the False return.
        logger.warning(
            "email_send_failed",
            to=_redact_email(to),
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
        return False
    except Exception as exc:  # pragma: no cover - defensive
        # Anything not covered above is unexpected. We still don't
        # raise — that would propagate into the refresh / alert path
        # and convert a notification glitch into a 500. Log loudly so
        # ops can investigate.
        logger.exception(
            "email_send_unexpected_error",
            to=_redact_email(to),
            error=str(exc)[:200],
        )
        return False
    return True


def _send_sync(msg: EmailMessage, cfg: Settings, timeout: float) -> None:
    """Synchronous SMTP transaction — runs inside the thread pool.

    Kept as a free function (not a closure) so unit tests can patch it
    with ``unittest.mock.patch`` without juggling closure state.
    """
    # ``with`` ensures ``QUIT`` is sent on every exit (clean or raised);
    # smtplib otherwise leaves the relay holding the socket open until
    # its idle timeout.
    with smtplib.SMTP(
        host=cfg.uni_smtp_host,   # narrowed by caller
        port=cfg.uni_smtp_port,
        timeout=timeout,
    ) as smtp:
        if cfg.uni_smtp_use_tls:
            # STARTTLS upgrade — the 587 submission port speaks plain
            # SMTP until this call. Failing to upgrade on a server that
            # requires it is the #1 production foot-gun, so we keep
            # this on by default and let the operator opt out via
            # UNI_SMTP_USE_TLS=false.
            smtp.starttls()
        if cfg.uni_smtp_user and cfg.uni_smtp_password:
            # AUTH only when creds are provided. A self-hosted relay
            # restricted by IP / network may legitimately accept
            # unauthenticated submission.
            smtp.login(cfg.uni_smtp_user, cfg.uni_smtp_password)
        smtp.send_message(msg)


def _redact_email(addr: str) -> str:
    """Best-effort PII redaction for log lines.

    ``stanley@example.com`` → ``s***@example.com``. Logs land in
    structured storage that ops + on-call eyes can see, so we drop the
    local part rather than write the recipient verbatim.
    """
    if not addr or "@" not in addr:
        return "***"
    local, domain = addr.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


__all__ = ["send_email"]
