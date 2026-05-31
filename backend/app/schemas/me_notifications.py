"""Current-user notification preference DTOs.

Spec: 2026-05-19 13F TG notifications on new filing — Step 5.
Round 14: Email channel added (UNI_USER_003).

Each transport opt-in is a separate field — keeping them flat avoids
a JSONB envelope we'd have to validate on every PATCH and matches how
the columns live on ``users`` (``telegram_chat_id`` + ``notify_via_email``).
LINE / Webhook will follow the same additive pattern when those channels
actually ship.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel


class MeNotificationPreferencesUpdate(StrictModel):
    """PATCH ``/api/v1/me/notifications`` body.

    All fields are optional so the PATCH is genuinely partial — the
    client can flip the email toggle without re-sending the
    ``telegram_chat_id``. We distinguish "field omitted" from "field
    set to null" by using a sentinel-free Pydantic shape: a missing
    key in the JSON body stays as the model's default of ``None`` AND
    the corresponding column is NOT touched on the user row. The
    ``__fields_set__`` check inside the endpoint handles the
    omitted-vs-explicit-null distinction.

    Setting ``telegram_chat_id`` to JSON ``null`` is the canonical
    "stop sending me TG alerts" gesture (column becomes NULL, the
    dispatcher filters us out).

    Setting ``notify_via_email`` to ``false`` is the opt-out for the
    Email channel; the user's ``email`` column is unaffected.
    """

    telegram_chat_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Telegram chat ID (numeric string, e.g. '123456789') or "
            "channel handle (e.g. '@my_channel'). Use JSON null to clear."
        ),
    )
    notify_via_email: bool | None = Field(
        default=None,
        description=(
            "Opt into Email notifications via the user's primary "
            "``email`` address. Omit the field to leave the current "
            "value unchanged; ``false`` to opt out."
        ),
    )


class MeNotificationPreferencesResponse(BaseModel):
    """GET / PATCH response — current preferences.

    Returned by both endpoints so the client can confirm the persisted
    state without re-fetching.
    """

    telegram_chat_id: str | None
    notify_via_email: bool
