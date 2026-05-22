"""Notifications module — outbound channels (Telegram first).

Spec: 2026-05-19 13F TG notifications on new filing.

Why a fresh ``app.modules.notifications`` package next to the legacy
``app.modules.notifier`` package?

- ``app.modules.notifier.telegram.TelegramNotifier`` wraps
  ``python-telegram-bot``'s full ``Bot`` class. It is a singleton-style
  client bound to one chat_id at construction time — fine for the
  legacy single-user notifier scheduler, but the wrong shape for
  per-user fan-out where the chat_id is a query result, not a config
  constant.
- We need a thin, stateless ``send_telegram_message(token, chat_id,
  text)`` that can be called inside a loop over subscribers without
  instantiating one ``Bot`` per recipient. Raw HTTPX against the Bot
  API is the smallest correct primitive.
- Cross-repo (sports-prophet) reuse is explicitly out of scope —
  see CLAUDE.md and the design brief: separate token, separate code.
"""
from app.modules.notifications.telegram_sender import send_telegram_message

__all__ = ["send_telegram_message"]
