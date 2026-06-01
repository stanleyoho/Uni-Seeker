"""Subscription DTOs — /api/v1/institutional/filers (POST + GET).

Spec §5. `F13SubscribeRequest` accepts a CIK string + optional name;
when the caller supplies a CIK we haven't ingested yet, the service
creates the filer row idempotently (`F13SubscriptionService.subscribe`).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel
from app.schemas.institutional.filer import F13FilerResponse


class F13SubscribeRequest(StrictModel):
    """POST /institutional/filers body.

    `cik` is the canonical 10-digit zero-padded form; service layer
    normalises before persisting. `name` is required when the filer is
    not yet in the local DB — the underlying `f13_filers.name` column
    is NOT NULL.
    """

    cik: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Required when the CIK is not yet in the local DB "
            "(f13_filers.name is NOT NULL). For known CIKs name is "
            "optional. Missing name on an unknown CIK → 422 "
            "f13_invalid_input."
        ),
    )
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


# ── Bulk subscribe ──────────────────────────────────────────────────────


class F13BulkSubscribeRequestItem(StrictModel):
    """One row in `POST /institutional/filers/bulk`.

    `cik` is required (the service normalises to 10-digit padded form;
    invalid CIKs land in the response's `errors[]` envelope rather than
    short-circuiting the whole batch). `name` is optional — when
    missing, the service tries `EdgarClient.get_filer_metadata(cik)`.
    """

    cik: str = Field(..., min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=255)


class F13BulkSubscribeRequest(StrictModel):
    """Bulk-subscribe up to 20 filers in one request.

    Validation rules (Pydantic):
      - 1..20 items per call. The cap mirrors `/watchlist/bulk` (Round
        6) — keeps one transaction reasonable in size and protects Free
        tier users from blowing past their 1-filer cap with a single
        large paste.
    """

    items: list[F13BulkSubscribeRequestItem] = Field(..., min_length=1, max_length=20)


class F13BulkSubscribeError(BaseModel):
    """Per-row failure inside the bulk-subscribe envelope.

    `reason` is a snake_case identifier:
      - `invalid_cik`           — non-digit input / failed normalisation
      - `edgar_lookup_failed`   — EDGAR metadata call failed (no `name`
                                  supplied and we couldn't auto-resolve)
      - `unknown`               — defensive catch-all
    """

    cik: str
    reason: str


class F13BulkSubscribeResponse(BaseModel):
    """Envelope for `POST /institutional/filers/bulk`.

    Three disjoint lists by canonical 10-digit CIK:
      - `subscribed`         — newly inserted F13Filer rows
      - `skipped_duplicates` — CIKs already on user's subscription list
      - `errors`             — per-row failures (no INSERT happened)

    Quota errors (403 limit_exceeded:max_tracked_filers) are NOT
    returned in this envelope — they short-circuit the whole batch with
    an HTTPException BEFORE any row is inserted.
    """

    subscribed: list[F13FilerResponse]
    skipped_duplicates: list[str]
    errors: list[F13BulkSubscribeError]


# ── Per-subscription preferences ────────────────────────────────────────


class F13SubscriptionPreferencesUpdate(StrictModel):
    """PATCH `/institutional/filers/{filer_id}/preferences` body.

    Currently a single-boolean toggle (notify_on_new_filing) but
    modelled as a PATCH body so future fields (e.g. email digest
    frequency, custom message template) can be added additively
    without breaking clients.
    """

    notify_on_new_filing: bool


class F13SubscriptionPreferencesResponse(BaseModel):
    """Returned by GET / PATCH preferences — the persisted state."""

    filer_id: int
    notify_on_new_filing: bool
