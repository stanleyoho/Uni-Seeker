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

from typing import TYPE_CHECKING

from app.config import settings
from app.modules.billing.tier_limits import get_limit
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


class F13SubscriptionService:
    """Subscription lifecycle.

    One instance per request. The injected `AsyncSession` is the
    transaction boundary; the injected `User` is the requesting
    principal — every read/write is scoped to `user.id`.
    """

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._filer_repo = F13FilerRepo(db)
        self._sub_repo = F13UserSubscriptionRepo(db)

    # ── tier guards (spec §9 service-level second line) ─────────────────

    async def _assert_filer_quota(self) -> None:
        """Raise `F13TierLimitExceeded` if adding one more subscription
        would push the user over `max_tracked_filers` for their tier.

        Bypassed when `enable_monetization=False` to mirror
        `tier_limits.tier_guard` behaviour.
        """
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_tracked_filers")
        if limit is None:
            return  # PRO / unlimited
        current = await self._sub_repo.count_by_user(self._user.id)
        if current >= limit:
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
                raise F13FilerNotFound(
                    f"filer_id={cik_or_filer_id} not found"
                )
        else:
            if not name:
                raise ValueError(
                    "name is required when subscribing by CIK string"
                )
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
        await self._sub_repo.subscribe(
            user_id=self._user.id, filer_id=filer.id
        )
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
        deleted = await self._sub_repo.unsubscribe(
            user_id=self._user.id, filer_id=filer_id
        )
        if not deleted:
            raise F13FilerNotFound(
                f"subscription to filer_id={filer_id} not found"
            )
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
        return await self._sub_repo.is_subscribed(
            self._user.id, filer_id
        )
