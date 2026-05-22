"""Current-user notification preference DTOs.

Spec: 2026-05-19 13F TG notifications on new filing — Step 5.

These are deliberately a single-channel shape (Telegram only) — Email
/ LINE / Webhook are advertised by ``/notifications/channels`` as
``coming_soon`` and will get their own preference fields when the
channels actually ship. Keeping the v1 schema small avoids API
churn from a speculative envelope.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MeNotificationPreferencesUpdate(BaseModel):
    """PATCH ``/api/v1/me/notifications`` body.

    Setting ``telegram_chat_id`` to ``None`` (i.e. explicit JSON
    ``null``) is the canonical "stop sending me TG alerts" gesture —
    the column becomes NULL and the notification service filters us
    out via ``telegram_chat_id IS NOT NULL`` (see
    ``F13NotificationService``).

    Length cap mirrors the ``users.telegram_chat_id`` column
    (VARCHAR(64)) so Pydantic 400s the client before we hit the DB
    truncation error.
    """

    telegram_chat_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Telegram chat ID (numeric string, e.g. '123456789') or "
            "channel handle (e.g. '@my_channel'). Use JSON null to clear."
        ),
    )


class MeNotificationPreferencesResponse(BaseModel):
    """GET / PATCH response — current preferences.

    Returned by both endpoints so the client can confirm the persisted
    state without re-fetching.
    """

    telegram_chat_id: str | None
