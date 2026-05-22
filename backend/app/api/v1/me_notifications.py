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

    Semantics:
      - body.telegram_chat_id = ``"12345"`` → set the column.
      - body.telegram_chat_id = ``None``    → clear the column.

    The PATCH verb is intentional: a future ``email``, ``line``, etc.
    field would be additive and only set when the client passes it.
    For now there is only one field so PATCH and PUT would behave
    identically — we still expose PATCH to lock in the additive
    semantics for v2.
    """
    before = {"telegram_chat_id": user.telegram_chat_id}
    user.telegram_chat_id = body.telegram_chat_id

    await log_audit_event(
        db,
        action="me_notifications_updated",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        before_state=before,
        after_state={"telegram_chat_id": user.telegram_chat_id},
    )
    await db.commit()
    await db.refresh(user)
    return MeNotificationPreferencesResponse(
        telegram_chat_id=user.telegram_chat_id,
    )
