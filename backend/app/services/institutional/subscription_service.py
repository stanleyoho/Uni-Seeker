"""F13SubscriptionService — user → filer subscription lifecycle.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2, §8 (tier guard), §9 (service-level second-line).

Responsibilities:
- Subscribe / unsubscribe / list — single source of truth for the
  user's "my filers" list.
- Tier quota check (`max_tracked_filers` per Q5 — Free 1 / Basic 5 /
  Pro unlimited) at the service layer as the second line of defense
  (first line is the FastAPI `tier_guard(...)` dependency in Batch C).
- Idempotent filer resolution: when the caller supplies a CIK string
  for a filer we haven't ingested yet, we create the row first.
- Audit log on every mutation.

Transaction boundary: the API layer commits after the service call
returns. We `flush` on every repo write so subsequent reads in the
same coroutine see the change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.modules.billing.tier_limits import get_limit
from app.modules.institutional.edgar_client import (
    EdgarTransientError,
    _pad_cik,
)
from app.repositories.institutional import (
    F13FilerRepo,
    F13UserSubscriptionRepo,
)
from app.services.audit import log_audit_event
from app.services.institutional.exceptions import (
    F13FilerNotFound,
    F13SubscriptionExists,
    F13TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.institutional.filer import F13Filer
    from app.models.user import User
    from app.modules.institutional.edgar_client import EdgarClient

logger = logging.getLogger(__name__)


class F13SubscriptionService:
    """Subscription lifecycle.

    One instance per request. The injected `AsyncSession` is the
    transaction boundary; the injected `User` is the requesting
    principal — every read/write is scoped to `user.id`.
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        edgar: EdgarClient | None = None,
    ) -> None:
        self._db = db
        self._user = user
        self._edgar = edgar
        self._filer_repo = F13FilerRepo(db)
        self._sub_repo = F13UserSubscriptionRepo(db)

    # ── tier guards (spec §9 service-level second line) ─────────────────

    async def _assert_filer_quota(self, delta: int = 1) -> None:
        """Raise `F13TierLimitExceeded` if adding `delta` more subscriptions
        would push the user over `max_tracked_filers` for their tier.

        `delta` defaults to 1 (single-subscribe path). For bulk_subscribe,
        the caller passes the count of NEW unique CIKs that would be
        inserted so the whole batch can be rejected atomically before any
        INSERT lands — matches the watchlist bulk endpoint's quota
        semantics (Round 6).

        Bypassed when `enable_monetization=False` to mirror
        `tier_limits.tier_guard` behaviour.
        """
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_tracked_filers")
        if limit is None:
            return  # PRO / unlimited
        current = await self._sub_repo.count_by_user(self._user.id)
        if current + delta > limit:
            raise F13TierLimitExceeded(
                limit_key="max_tracked_filers",
                current=current,
                limit=limit,
            )

    # ── public API ──────────────────────────────────────────────────────

    async def subscribe(
        self,
        cik_or_filer_id: str | int,
        name: str | None = None,
        legal_name: str | None = None,
    ) -> F13Filer:
        """Subscribe the current user to a filer.

        `cik_or_filer_id` polymorphism:
          - `int` → existing filer id; raises `F13FilerNotFound` if not.
          - `str` → CIK string; we `get_or_create_by_cik` with the
            supplied `name`. `name` is required in the str branch
            because a new filer row cannot be created without one
            (DB NOT NULL constraint).

        Order of checks (spec §9):
          1. Resolve / create filer.
          2. Tier quota (`max_tracked_filers`).
          3. Reject duplicate subscription.
          4. INSERT + audit log.

        Raises:
            F13FilerNotFound      — int filer_id missing.
            ValueError            — str CIK supplied without name.
            F13TierLimitExceeded  — quota exhausted.
            F13SubscriptionExists — already subscribed.
        """
        # Step 1: resolve filer (creating on-demand for str CIK)
        if isinstance(cik_or_filer_id, int):
            filer = await self._filer_repo.get_by_id(cik_or_filer_id)
            if filer is None:
                raise F13FilerNotFound(f"filer_id={cik_or_filer_id} not found")
        else:
            if not name:
                raise ValueError("name is required when subscribing by CIK string")
            filer, _ = await self._filer_repo.get_or_create_by_cik(
                cik=cik_or_filer_id,
                name=name,
                legal_name=legal_name,
            )

        # Step 2: tier quota
        await self._assert_filer_quota()

        # Step 3: duplicate check (clean 409 instead of DB IntegrityError)
        if await self._sub_repo.is_subscribed(self._user.id, filer.id):
            raise F13SubscriptionExists(filer_id=filer.id)

        # Step 4: INSERT + audit
        await self._sub_repo.subscribe(user_id=self._user.id, filer_id=filer.id)
        await log_audit_event(
            self._db,
            action="f13_filer_subscribed",
            user_id=self._user.id,
            resource_type="f13_filer",
            resource_id=str(filer.id),
            after_state={"cik": filer.cik, "name": filer.name},
        )
        return filer

    async def unsubscribe(self, filer_id: int) -> None:
        """Remove the (user, filer) subscription.

        Raises:
            F13FilerNotFound — when the user was not subscribed to this
                filer (same 404/403 collapse as portfolio module). We
                still issue an audit log because the attempt is
                noteworthy from a security perspective, but only on the
                successful path — failed attempts at non-existent rows
                are not audited (matches portfolio convention).
        """
        deleted = await self._sub_repo.unsubscribe(user_id=self._user.id, filer_id=filer_id)
        if not deleted:
            raise F13FilerNotFound(f"subscription to filer_id={filer_id} not found")
        await log_audit_event(
            self._db,
            action="f13_filer_unsubscribed",
            user_id=self._user.id,
            resource_type="f13_filer",
            resource_id=str(filer_id),
        )

    async def list_subscriptions(self) -> list[F13Filer]:
        """Filers the current user is subscribed to (ordered by name)."""
        return await self._sub_repo.list_filers_by_user(self._user.id)

    async def get_subscription_status(self, filer_id: int) -> bool:
        """Convenience predicate for the API layer."""
        return await self._sub_repo.is_subscribed(self._user.id, filer_id)

    # ── bulk subscribe ──────────────────────────────────────────────────

    async def bulk_subscribe(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Subscribe to multiple filers in one atomic transaction.

        `items` is a list of `{"cik": str, "name": str | None}` dicts —
        normalised + de-duplicated within the request before INSERTs
        land. The flow mirrors `POST /watchlist/bulk` (Round 6):

          1. Validate count (1..20). Pydantic enforces, this is a
             defensive belt-and-suspenders.
          2. Normalise + dedupe input CIKs (10-digit zero-padded).
             Invalid CIKs become per-row `errors[reason=invalid_cik]`.
          3. Split request CIKs into already-subscribed (skipped) vs.
             candidates to insert.
          4. **Atomic quota pre-check**: project
             `current_subscriptions + len(new_unique_ciks) > limit` and
             raise `F13TierLimitExceeded` before any INSERT lands. The
             whole batch is rejected; the API layer returns 403.
          5. For each candidate:
             a. Resolve filer row via `get_or_create_by_cik`. If `name`
                is missing, fetch metadata via the injected EdgarClient.
                On EDGAR failure → per-row error, skip insert.
             b. INSERT subscription. Per-row exceptions during INSERT
                raise out → the caller's transaction rolls the whole
                batch back (atomic contract — partial commits would be
                confusing UX).
             c. Audit log on success.
          6. Return `{subscribed, skipped_duplicates, errors}` envelope.

        Atomicity model: this method uses ONE `AsyncSession` (injected
        via __init__). The API layer commits AFTER this method returns
        successfully; any exception bubbles out and the API layer
        rolls back. No partial states.
        """
        subscribed: list[F13Filer] = []
        skipped_duplicates: list[str] = []
        errors: list[dict[str, str]] = []

        # ── Step 1: defensive count check (Pydantic already enforces) ──
        if not items:
            return {
                "subscribed": [],
                "skipped_duplicates": [],
                "errors": [],
            }
        if len(items) > 20:
            raise ValueError("bulk_subscribe accepts at most 20 items")

        # ── Step 2: normalise + request-level dedupe ───────────────────
        # `cik_to_name` preserves the FIRST supplied name for a CIK so
        # that duplicate input rows don't override with empty names.
        cik_to_name: dict[str, str | None] = {}
        seen: set[str] = set()
        for raw in items:
            raw_cik = raw.get("cik") if isinstance(raw, dict) else None
            if not isinstance(raw_cik, str) or not raw_cik.strip():
                errors.append({"cik": str(raw_cik or ""), "reason": "invalid_cik"})
                continue
            try:
                normalised = _pad_cik(raw_cik)
            except ValueError:
                errors.append({"cik": raw_cik, "reason": "invalid_cik"})
                continue
            if normalised in seen:
                # Request-level dedupe: do not double-process the same
                # CIK. We do NOT report this in skipped_duplicates —
                # that list is reserved for filers the user already
                # subscribed to BEFORE this call (matches watchlist).
                continue
            seen.add(normalised)
            name = raw.get("name") if isinstance(raw, dict) else None
            cik_to_name[normalised] = (
                name.strip() if isinstance(name, str) and name.strip() else None
            )

        normalised_ciks = list(cik_to_name.keys())

        # ── Step 3: split already-subscribed vs candidates ─────────────
        # Cheap path: count via repo + per-CIK `is_subscribed`. Phase 1
        # batch size cap is 20 so the round-trip cost is bounded.
        already_subscribed_ciks: list[str] = []
        candidate_ciks: list[str] = []
        for cik in normalised_ciks:
            filer = await self._filer_repo.get_by_cik(cik)
            if filer is not None and await self._sub_repo.is_subscribed(self._user.id, filer.id):
                already_subscribed_ciks.append(cik)
            else:
                candidate_ciks.append(cik)
        skipped_duplicates.extend(already_subscribed_ciks)

        # ── Step 4: atomic tier-quota pre-check on candidate count ─────
        if candidate_ciks:
            await self._assert_filer_quota(delta=len(candidate_ciks))

        # ── Step 5: resolve + INSERT each candidate ────────────────────
        for cik in candidate_ciks:
            name = cik_to_name.get(cik)
            legal_name: str | None = None

            # 5a: EDGAR metadata fallback when name missing.
            if not name:
                if self._edgar is None:
                    # No EDGAR client wired in. Fall back to the CIK
                    # itself so we don't violate the NOT NULL constraint
                    # — caller can rename later. Not ideal, but graceful.
                    name = cik
                else:
                    try:
                        meta = await self._edgar.get_filer_metadata(cik)
                        name = meta.name or cik
                        legal_name = meta.legal_name
                    except (EdgarTransientError, Exception) as exc:
                        logger.warning(
                            "bulk_subscribe_edgar_lookup_failed cik=%s err=%s",
                            cik,
                            exc,
                        )
                        errors.append({"cik": cik, "reason": "edgar_lookup_failed"})
                        continue

            # 5b: get_or_create_by_cik + INSERT subscription. Any
            # exception here bubbles out → API layer rolls back the
            # transaction (atomic batch contract).
            filer, _was_created = await self._filer_repo.get_or_create_by_cik(
                cik=cik,
                name=name,
                legal_name=legal_name,
            )
            await self._sub_repo.subscribe(user_id=self._user.id, filer_id=filer.id)
            await log_audit_event(
                self._db,
                action="f13_filer_subscribed",
                user_id=self._user.id,
                resource_type="f13_filer",
                resource_id=str(filer.id),
                after_state={
                    "cik": filer.cik,
                    "name": filer.name,
                    "via": "bulk",
                },
            )
            subscribed.append(filer)

        return {
            "subscribed": subscribed,
            "skipped_duplicates": skipped_duplicates,
            "errors": errors,
        }
