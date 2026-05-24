"""Telegram send-only client via raw Bot API (httpx).

Why not ``python-telegram-bot`` (already in deps for the legacy notifier):
the heavyweight ``telegram.Bot`` class manages an internal HTTP pool and
a JobQueue we don't need for one-way notifications. A 30-line wrapper
around ``POST /bot{TOKEN}/sendMessage`` is sufficient, easier to mock in
tests, and keeps the import surface of this module tiny.

Why not reuse sports-prophet's bot: cross-repo coupling is forbidden
(see CLAUDE.md). Each service ships with its own token + sender.

Failure semantics: this is a *side-effect* module — callers (the 13F
notification service) MUST NOT raise into the refresh path on a TG
failure. We therefore return a plain ``bool`` and log every error path.
The caller counts ``False`` returns as ``errors`` for the audit row.
"""

from __future__ import annotations

import httpx

from app.obs.logging import get_logger

logger = get_logger(component="telegram_sender")


# Telegram API timeout: be generous enough to survive a slow link from
# our PoP but tight enough to not block the refresh path for long. 10 s
# is the documented "long enough but not forever" value the Bot API
# itself recommends.
_DEFAULT_TIMEOUT_SECONDS = 10.0
_API_BASE = "https://api.telegram.org"


async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """POST ``/bot{TOKEN}/sendMessage``; return True iff Telegram says OK.

    Args:
        bot_token: Telegram Bot API token. Empty string short-circuits
            to ``False`` so a missing config value never produces an
            HTTP call (cheap defensive guard for tests + dev).
        chat_id: Numeric chat ID (as string) or ``@username``.
        text: Message body (≤4096 chars; we do not truncate here — the
            caller is responsible for fitting the template).
        parse_mode: ``"HTML"`` (default) or ``"MarkdownV2"``. We default
            to HTML because the 13F message template uses ``<b>``.
        disable_notification: silent push (``True``) or play sound
            (``False``, default).
        timeout: per-request timeout in seconds.
        client: optional pre-opened ``httpx.AsyncClient`` for tests; if
            ``None`` we open one per call.

    Returns:
        ``True`` on 2xx + ``{"ok": true}``; ``False`` on every other
        outcome (transport error, 4xx/5xx, ``ok: false``, empty token).
    """
    if not bot_token:
        # Empty config — common in unit tests + first-boot dev. Don't
        # spam logs at warning level: this is the documented "off"
        # state. Caller already knows to skip when False.
        logger.debug("tg_send_skipped_empty_token", chat_id=chat_id)
        return False
    if not chat_id:
        # Defensive: a None/empty chat_id would 400 with "chat not
        # found" — short-circuit before paying the round trip.
        logger.debug("tg_send_skipped_empty_chat_id")
        return False

    url = f"{_API_BASE}/bot{bot_token}/sendMessage"
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_notification": disable_notification,
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
    try:
        try:
            response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            # Transport-level failure (DNS, TLS, connect, read, timeout).
            # Logged at warning because notifications are best-effort.
            logger.warning(
                "tg_send_transport_error",
                chat_id=chat_id,
                error=str(exc),
            )
            return False

        if response.status_code >= 400:
            # 429 (rate limit) and 401 (bad token) both land here.
            # We log status + a short body excerpt so ops can tell them
            # apart without leaking the full Telegram body which may
            # contain user-supplied text echoed back.
            logger.warning(
                "tg_send_http_error",
                chat_id=chat_id,
                status=response.status_code,
                body=response.text[:200],
            )
            return False

        try:
            data = response.json()
        except ValueError:
            logger.warning(
                "tg_send_invalid_json",
                chat_id=chat_id,
                body=response.text[:200],
            )
            return False

        # Bot API quirk: HTTP 200 + {"ok": false, "error_code": ...} is
        # the canonical "bad chat_id / parse error" shape. Treat it as
        # a soft failure.
        if not data.get("ok", False):
            logger.warning(
                "tg_send_api_not_ok",
                chat_id=chat_id,
                error_code=data.get("error_code"),
                description=data.get("description"),
            )
            return False
        return True
    finally:
        if owns_client:
            await client.aclose()


__all__ = ["send_telegram_message"]
