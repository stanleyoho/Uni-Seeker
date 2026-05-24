"""Multi-channel notification dispatcher.

One entry point ``dispatch_notification`` that routes a single logical
event (a 13F filing, an alert rule firing, etc.) to every channel the
user has opted into. Today's channels: Telegram + Email. Adding a new
channel (LINE / Webhook) is a single ``if user.<flag>:`` block here —
the call sites do not change.

Design contract:

  - The dispatcher knows nothing about WHAT it is sending. The caller
    composes the title + bodies and supplies a deep link; the
    dispatcher just fans out the bytes.
  - Per-channel sends are best-effort. A failure on one channel does
    NOT abort the other channel. The return value carries per-channel
    booleans + aggregate counters so the caller can log a uniform
    audit row.
  - The dispatcher does NOT write audit rows itself. The caller already
    has the resource context (filer_id, rule_id, …) and is in the
    right place to log the aggregate. Writing audit here would double
    up on the existing ``f13_notifications_sent`` row.

Why a plain function and not a class:

  - Stateless. No caches, no per-instance config — the SMTP / TG
    settings live on the global ``settings`` singleton, which the
    sender modules read directly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from app.modules.notifications.email_sender import send_email
from app.modules.notifications.telegram_sender import send_telegram_message
from app.obs.logging import get_logger

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(component="notification_dispatcher")


async def dispatch_notification(
    user: "User",
    *,
    title: str,
    body_text: str,
    body_html: str | None = None,
    tg_text: str | None = None,
    deep_link: str | None = None,
) -> dict[str, int | bool]:
    """Fan out a single event to every channel the user has enabled.

    Channel eligibility (per-user opt-in):

      - **Telegram**: requires ``user.telegram_chat_id`` set AND
        ``settings.uni_telegram_bot_token`` non-empty.
      - **Email**: requires ``user.notify_via_email = True`` AND a
        non-empty ``user.email``. SMTP-side config (host / from) is
        checked inside ``send_email`` and produces a ``False`` return
        without raising; the dispatcher counts that as an error.

    Args:
        user: The ORM user row. We read ``telegram_chat_id``,
            ``notify_via_email``, ``email`` — none of which trigger a
            lazy load.
        title: Short headline. Used as the Email ``Subject:`` and as
            the first line of the Telegram message (when ``tg_text``
            is not supplied).
        body_text: Plain-text body. Becomes the Email ``text/plain``
            part and the Telegram body when no dedicated TG text is
            provided.
        body_html: Optional ``text/html`` alternative for Email. The
            recipient's client picks the richer rendering; the plain
            part stays the fallback.
        tg_text: Optional pre-rendered Telegram body (e.g. the
            existing F13/alert HTML template). When ``None`` we
            synthesise ``"<b>{title}</b>\\n{body_text}\\n\\n{link}"``.
        deep_link: Optional URL appended to the plain-text + Telegram
            bodies as a "查看詳情" / "See details" footer. Caller
            composes the URL with ``settings.app_url``.

    Returns:
        ``{"tg_sent": bool, "email_sent": bool,
        "channels_attempted": int, "channels_succeeded": int}`` —
        suitable for direct inclusion in an audit row's
        ``after_state``.
    """
    results: dict[str, int | bool] = {
        "tg_sent": False,
        "email_sent": False,
        "channels_attempted": 0,
        "channels_succeeded": 0,
    }

    # ── Telegram ──────────────────────────────────────────────────────
    # Eligibility check up-front so we don't even count "attempted" if
    # the user never bound a chat id. That mirrors the F13 service's
    # original skip semantics.
    bot_token = settings.uni_telegram_bot_token
    chat_id = user.telegram_chat_id
    if bot_token and chat_id:
        results["channels_attempted"] = int(results["channels_attempted"]) + 1
        text = tg_text if tg_text is not None else _compose_tg(
            title=title, body_text=body_text, deep_link=deep_link,
        )
        ok = await send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=text,
        )
        if ok:
            results["tg_sent"] = True
            results["channels_succeeded"] = (
                int(results["channels_succeeded"]) + 1
            )
        else:
            # Sender already logged the reason at warning; we re-log
            # at debug with the user_id so cross-channel correlation
            # is one grep away in production.
            logger.debug(
                "dispatch_tg_send_failed",
                user_id=getattr(user, "id", None),
            )

    # ── Email ─────────────────────────────────────────────────────────
    if user.notify_via_email and user.email:
        results["channels_attempted"] = int(results["channels_attempted"]) + 1
        # Append the deep link to the plain-text body so non-HTML
        # clients still see it. The HTML body is the caller's
        # responsibility — if they want an anchor tag they pass it in
        # ``body_html`` already styled.
        text_with_link = body_text
        if deep_link:
            text_with_link = f"{body_text}\n\n查看詳情: {deep_link}"
        ok = await send_email(
            to=user.email,
            subject=title,
            body_text=text_with_link,
            body_html=body_html,
        )
        if ok:
            results["email_sent"] = True
            results["channels_succeeded"] = (
                int(results["channels_succeeded"]) + 1
            )
        else:
            logger.debug(
                "dispatch_email_send_failed",
                user_id=getattr(user, "id", None),
            )

    return results


def _compose_tg(
    *,
    title: str,
    body_text: str,
    deep_link: str | None,
) -> str:
    """Build a default Telegram body when the caller did not supply
    one. The existing F13 + alert call sites pass their own
    ``tg_text`` so this code path is only exercised by future
    integrations that don't have a curated template yet.

    HTML parse mode — matches what ``send_telegram_message`` defaults
    to. We escape the title so any caller-supplied ``<`` / ``>`` in
    the headline doesn't break the Bot API parser.
    """
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    footer = f"\n\n看詳情: {deep_link}" if deep_link else ""
    return f"<b>{safe_title}</b>\n{body_text}{footer}"


__all__ = ["dispatch_notification"]
