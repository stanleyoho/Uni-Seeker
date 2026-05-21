"""F13UserSubscriptionRepo — user × filer relationship.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§4.3 Table 2, §6.3.

**Isolation strategy — structural `user_id` filter on every method.**
This is the table that carries the user dimension for the 13F module.
Cross-user reads / writes are impossible by construction: every public
method takes `user_id` and applies it as a WHERE clause.

CRUD only — no business logic, no tier checks (spec §11 R3).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.subscription import F13UserSubscription

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class F13UserSubscriptionRepo:
    """CRUD over `f13_user_subscriptions`.

    All methods flush but do not commit; service layer owns the
    transaction boundary.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def subscribe(
        self,
        user_id: int,
        filer_id: int,
        notify_on_new_filing: bool = True,
    ) -> F13UserSubscription:
        """INSERT a subscription row. Caller (service) must have already
        checked the (user_id, filer_id) is not already present — the DB
        UNIQUE constraint is a safety net but raising at the repo
        boundary leaks `IntegrityError` semantics into the API layer.
        """
        sub = F13UserSubscription(
            user_id=user_id,
            filer_id=filer_id,
            notify_on_new_filing=notify_on_new_filing,
        )
        self.db.add(sub)
        await self.db.flush()
        await self.db.refresh(sub)
        return sub

    async def unsubscribe(self, user_id: int, filer_id: int) -> bool:
        """DELETE the (user, filer) sub row iff it belongs to `user_id`.

        Returns True when a row was deleted, False when none matched —
        the service distinguishes "not subscribed" from "404 filer"
        before calling this.
        """
        result = await self.db.execute(
            delete(F13UserSubscription).where(
                F13UserSubscription.user_id == user_id,
                F13UserSubscription.filer_id == filer_id,
            )
        )
        await self.db.flush()
        return (result.rowcount or 0) > 0

    async def list_by_user(
        self, user_id: int
    ) -> list[F13UserSubscription]:
        """All subscriptions owned by `user_id`, with `filer` eager-loaded.

        Eager-loading `filer` via `selectinload` lets callers render the
        "my filers" page without an N+1 query per row.
        """
        result = await self.db.execute(
            select(F13UserSubscription)
            .options(selectinload(F13UserSubscription.filer))
            .where(F13UserSubscription.user_id == user_id)
            .order_by(F13UserSubscription.id.asc())
        )
        return list(result.scalars().all())

    async def list_filers_by_user(self, user_id: int) -> list[F13Filer]:
        """Convenience: return the F13Filer rows the user is subscribed to.

        Equivalent to `[s.filer for s in list_by_user(...)]` but via a
        direct JOIN — keeps the SQL surface inspectable in EXPLAIN.
        """
        result = await self.db.execute(
            select(F13Filer)
            .join(
                F13UserSubscription,
                F13UserSubscription.filer_id == F13Filer.id,
            )
            .where(F13UserSubscription.user_id == user_id)
            .order_by(F13Filer.name.asc())
        )
        return list(result.scalars().all())

    async def is_subscribed(self, user_id: int, filer_id: int) -> bool:
        """Cheap existence check used by access-control gates in
        `F13FilingService.list_filings_for_filer` etc."""
        result = await self.db.execute(
            select(F13UserSubscription.id).where(
                F13UserSubscription.user_id == user_id,
                F13UserSubscription.filer_id == filer_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def count_by_user(self, user_id: int) -> int:
        """Number of filers tracked by `user_id`. Used by the tier
        quota check (`max_tracked_filers`) at the service layer.
        """
        result = await self.db.execute(
            select(func.count(F13UserSubscription.id)).where(
                F13UserSubscription.user_id == user_id
            )
        )
        return int(result.scalar() or 0)
