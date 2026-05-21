"""Subscription DTOs — /api/v1/institutional/filers (POST + GET).

Spec §5. `F13SubscribeRequest` accepts a CIK string + optional name;
when the caller supplies a CIK we haven't ingested yet, the service
creates the filer row idempotently (`F13SubscriptionService.subscribe`).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.institutional.filer import F13FilerResponse


class F13SubscribeRequest(BaseModel):
    """POST /institutional/filers body.

    `cik` is the canonical 10-digit zero-padded form; service layer
    normalises before persisting. `name` is required when the filer is
    not yet in the local DB — the underlying `f13_filers.name` column
    is NOT NULL.
    """

    cik: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=255)
    legal_name: str | None = Field(default=None, max_length=500)


class F13SubscriptionResponse(BaseModel):
    """POST /institutional/filers response.

    Returns the resolved/created filer plus subscription metadata.
    `subscribed_at` is filled from `f13_user_subscriptions.subscribed_at`
    via the service helper.
    """

    filer: F13FilerResponse
    subscribed_at: datetime
    notify_on_new_filing: bool
