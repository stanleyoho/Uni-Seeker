"""Current-user notification preferences — /api/v1/me/notifications.

Spec: 2026-05-19 13F TG notifications on new filing — Step 5.

Endpoints:
  - ``GET  /api/v1/me/notifications``  — read current settings
  - ``PATCH /api/v1/me/notifications`` — update telegram_chat_id
                                          (null clears)

Why a dedicated ``/me/...`` router rather than reusing
``/api/v1/notifications``: the existing notifications router models
``NotificationRule`` (price alerts, screener summaries) which is a
different concern from per-user transport identifiers. Keeping the
two surfaces apart prevents the chat_id from accidentally getting
nested under a rule body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import require_auth
from app.models.user import User
from app.schemas.me_notifications import (
    MeNotificationPreferencesResponse,
    MeNotificationPreferencesUpdate,
)
from app.services.audit import log_audit_event

router = APIRouter(prefix="/me/notifications", tags=["me.notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.get(
    "",
    response_model=MeNotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_me_notifications(
    user: UserDep,
) -> MeNotificationPreferencesResponse:
    """Return the current user's notification preferences."""
    return MeNotificationPreferencesResponse(
        telegram_chat_id=user.telegram_chat_id,
        notify_via_email=user.notify_via_email,
    )


@router.patch(
    "",
    response_model=MeNotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
)
async def patch_me_notifications(
    body: MeNotificationPreferencesUpdate,
    db: DbDep,
    user: UserDep,
) -> MeNotificationPreferencesResponse:
    """Update the current user's notification preferences.

    Round-14 PATCH semantics (truly partial):

      - Field OMITTED in the JSON body → column unchanged.
      - ``telegram_chat_id = "12345"``  → set the column.
      - ``telegram_chat_id = null``     → clear the column.
      - ``notify_via_email = true / false`` → set the opt-in flag.

    We distinguish "omitted" from "explicit null" via Pydantic's
    ``model_fields_set`` — only fields the client actually included
    in the JSON body are written. This keeps the front-end safe to
    PATCH a single toggle without round-tripping the other channels.
    """
    before = {
        "telegram_chat_id": user.telegram_chat_id,
        "notify_via_email": user.notify_via_email,
    }
    fields_set = body.model_fields_set
    if "telegram_chat_id" in fields_set:
        user.telegram_chat_id = body.telegram_chat_id
    if "notify_via_email" in fields_set and body.notify_via_email is not None:
        user.notify_via_email = body.notify_via_email

    await log_audit_event(
        db,
        action="me_notifications_updated",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        before_state=before,
        after_state={
            "telegram_chat_id": user.telegram_chat_id,
            "notify_via_email": user.notify_via_email,
        },
    )
    await db.commit()
    await db.refresh(user)
    return MeNotificationPreferencesResponse(
        telegram_chat_id=user.telegram_chat_id,
        notify_via_email=user.notify_via_email,
    )
