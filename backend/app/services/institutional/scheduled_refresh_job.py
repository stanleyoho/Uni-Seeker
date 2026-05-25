"""Scheduled 13F refresh job — tier-driven auto-refresh of subscribed filers.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2 + §9 (tier policy) + §11 R6 (idempotency).

Cadence per Q1 / tier policy:

  PRO    — daily   06:00 UTC   (skip filers refreshed in last 12 h)
  BASIC  — weekly  Sun 06:00   (skip filers refreshed in last 6 days)
  FREE   — NEVER auto-refreshed (on-demand only — by design Q1)

Why 06:00 UTC: SEC publishes 13F filings throughout the US business day;
06:00 UTC == 02:00 ET, well after the same-day filing window closes,
which maximises the chance that a "daily" run captures everything new
that landed the prior calendar day in the US.

Why a per-tier skip window?
- EDGAR's fair-use is 10 req/sec global (see ``EdgarRateLimiter``).
  A user-facing on-demand refresh always wins the rate budget; the
  scheduled job is the opportunistic side-channel, so it must never
  re-hammer a filer that just got refreshed manually. ``F13Filer.latest_filing_date``
  is the cheapest probe we have — it's denormalised at the tail of every
  successful refresh, so "filer.latest_filing_date >= today - N days"
  is a no-cost proxy for "we already have the freshest filing for this
  filer." The skip is conservative — better to skip and rely on the
  next cron cycle than to burn the rate budget on a no-op.

Anti-coupling contract:
- The two ``*_entrypoint`` functions are what APScheduler calls. They
  own their own DB session + ``EdgarClient`` so the scheduler is fully
  self-contained at runtime.
- The inner ``refresh_for_tier`` / ``daily_pro_refresh`` /
  ``weekly_basic_refresh`` take the session + client as parameters so
  tests can inject a ``MockEdgarClient`` against the shared
  ``db_session`` fixture without touching the scheduler module.
- ``F13RefreshInFlightError`` (raised by ``F13FilingService.refresh_filer``
  when a manual refresh holds the per-filer lock) is caught and counted
  as ``skipped`` — losing the race to a user request is the *correct*
  outcome, not an error.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.institutional.subscription import F13UserSubscription
from app.models.enums import UserTier
from app.models.user import User
from app.modules.institutional.edgar_client import EdgarClient
from app.services.institutional.exceptions import (
    F13EdgarError,
    F13FilerNotFoundError,
    F13RefreshInFlightError,
)
from app.services.institutional.filing_service import F13FilingService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)


# Defaults map cleanly onto the cron cadence:
#  - PRO runs every 24h, so a 12h skip window guarantees at most one
#    refresh per UTC day even if an operator manually triggers an extra run.
#  - BASIC runs weekly, so a 6-day skip window keeps the weekly tick from
#    re-refreshing a filer that a Pro user (sharing the same filer row)
#    pulled into freshness within the same week.
_PRO_SKIP_HOURS = 12
_BASIC_SKIP_HOURS = 24 * 6  # 144 — 6 days


__all__ = [
    "daily_pro_refresh",
    "daily_pro_refresh_entrypoint",
    "refresh_for_tier",
    "weekly_basic_refresh",
    "weekly_basic_refresh_entrypoint",
]


# ── core: refresh_for_tier ─────────────────────────────────────────────────


async def refresh_for_tier(
    db: AsyncSession,
    edgar_client: EdgarClient,
    tier: UserTier,
    *,
    skip_recent_hours: int,
    now: datetime | None = None,
) -> dict[str, int]:
    """Scan all users on ``tier`` and refresh each subscribed filer.

    A *filer* is shared across users (Q2), so we de-duplicate by filer_id
    across the entire tier — refreshing once benefits every subscribed
    user. The per-user audit row written inside ``refresh_filer`` is
    keyed to the first user who triggered the (de-duplicated) refresh
    on this cycle; that's good enough for the audit trail because the
    audit is "scheduler did a refresh," not "who would have asked for
    one." The user.id picked here is deterministic (smallest id first).

    Args:
        db: ``AsyncSession`` — caller owns the transaction (caller must
            ``commit``). The scheduler entrypoints do this.
        edgar_client: an *open* ``EdgarClient`` (already inside
            ``async with``).
        tier: ``UserTier.PRO`` or ``UserTier.BASIC``. ``FREE`` is
            explicitly rejected — see Q1 policy.
        skip_recent_hours: don't refresh filers whose
            ``latest_filing_date`` is within this many hours of ``now``.
            We use the date (not a timestamp column) because that's what
            ``F13Filer`` denormalises after each refresh; we coerce it
            to UTC-midnight and compare against ``now - hours``.
        now: injected wall clock for tests. Defaults to ``datetime.now(UTC)``.

    Returns:
        ``dict`` with the keys
        ``users_processed`` / ``filers_refreshed`` / ``filings_added``
        / ``holdings_added`` / ``skipped`` / ``errors``.
        ``skipped`` counts both "already fresh" and "lost race to
        on-demand refresh" — both are healthy outcomes.

    Raises:
        ``ValueError`` if ``tier`` is ``UserTier.FREE``. By design — Free
        users are on-demand-only and should never be scheduled.
    """
    if tier is UserTier.FREE:
        raise ValueError(
            "refresh_for_tier rejects FREE tier — Free users are on-demand-only by spec Q1."
        )

    if now is None:
        now = datetime.now(UTC)
    skip_floor_date = (now - timedelta(hours=skip_recent_hours)).date()

    # 1. Discover (user, subscriptions) for this tier in one round trip.
    #    Joining on F13UserSubscription would drop users with zero subs
    #    — exactly what we want: scheduler must not "process" users with
    #    nothing to refresh.
    stmt = (
        select(User)
        .join(F13UserSubscription, F13UserSubscription.user_id == User.id)
        .where(User.tier == tier)
        .distinct()
        .order_by(User.id.asc())
    )
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    users_processed = 0
    filers_refreshed = 0
    filings_added = 0
    holdings_added = 0
    skipped = 0
    errors = 0

    # De-dup across users: one filer_id may be tracked by many users on
    # the same tier; refresh it exactly once per cycle.
    seen_filer_ids: set[int] = set()

    for user in users:
        # Load this user's subscriptions with the filer eager-loaded so we
        # can inspect ``filer.latest_filing_date`` without an N+1.
        sub_result = await db.execute(
            select(F13UserSubscription)
            .options(selectinload(F13UserSubscription.filer))
            .where(F13UserSubscription.user_id == user.id)
            .order_by(F13UserSubscription.filer_id.asc())
        )
        subs = list(sub_result.scalars().all())
        if not subs:
            # Defensive — JOIN above shouldn't return such users, but a
            # delete-after-select race could.
            continue

        users_processed += 1
        # One service instance per (user, tier-loop). The service is
        # request-scoped by design and the per-filer lock lives at class
        # scope so concurrent instances still serialise correctly.
        service = F13FilingService(db, user, edgar_client)

        for sub in subs:
            filer = sub.filer
            if filer is None or filer.id in seen_filer_ids:
                continue
            seen_filer_ids.add(filer.id)

            # Skip if we've already seen a fresh filing for this filer
            # within the per-tier window. ``latest_filing_date`` is None
            # for brand-new subscriptions (we've never run a refresh yet)
            # — those MUST be refreshed, hence the explicit None check.
            if filer.latest_filing_date is not None and filer.latest_filing_date >= skip_floor_date:
                skipped += 1
                logger.debug(
                    "13f_scheduled_skip_recent",
                    filer_id=filer.id,
                    cik=filer.cik,
                    latest_filing_date=str(filer.latest_filing_date),
                    skip_floor=str(skip_floor_date),
                )
                continue

            try:
                result_counts = await service.refresh_filer(filer.id)
            except F13RefreshInFlightError:
                # User-driven manual refresh already holds the lock —
                # losing the race is the correct outcome.
                skipped += 1
                logger.info(
                    "13f_scheduled_skip_in_flight",
                    filer_id=filer.id,
                    cik=filer.cik,
                )
                continue
            except F13FilerNotFoundError:
                # Filer deleted between SELECT and refresh (very rare).
                skipped += 1
                continue
            except F13EdgarError as exc:
                # Upstream EDGAR failure — log + count and keep going.
                # Burning the whole cron run on one bad filer would be
                # operationally wasteful.
                errors += 1
                logger.warning(
                    "13f_scheduled_edgar_error",
                    filer_id=filer.id,
                    cik=filer.cik,
                    error=str(exc),
                    edgar_status=exc.edgar_status,
                )
                continue
            except Exception as exc:  # pragma: no cover - safety net
                errors += 1
                logger.exception(
                    "13f_scheduled_unexpected_error",
                    filer_id=filer.id,
                    cik=filer.cik,
                    error=str(exc),
                )
                continue

            filers_refreshed += 1
            filings_added += int(result_counts.get("filings_added", 0))
            holdings_added += int(result_counts.get("holdings_added", 0))

    return {
        "users_processed": users_processed,
        "filers_refreshed": filers_refreshed,
        "filings_added": filings_added,
        "holdings_added": holdings_added,
        "skipped": skipped,
        "errors": errors,
    }


# ── tier-specific wrappers (callable from tests + entrypoints) ────────────


async def daily_pro_refresh(
    db: AsyncSession,
    edgar_client: EdgarClient,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """06:00 UTC daily — PRO tier only. 12h skip window."""
    return await refresh_for_tier(
        db,
        edgar_client,
        UserTier.PRO,
        skip_recent_hours=_PRO_SKIP_HOURS,
        now=now,
    )


async def weekly_basic_refresh(
    db: AsyncSession,
    edgar_client: EdgarClient,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Sun 06:00 UTC weekly — BASIC tier only. 6-day skip window."""
    return await refresh_for_tier(
        db,
        edgar_client,
        UserTier.BASIC,
        skip_recent_hours=_BASIC_SKIP_HOURS,
        now=now,
    )


# ── APScheduler entrypoints ────────────────────────────────────────────────
#
# These are the two callables that APScheduler invokes from
# ``app.scheduler``. They are zero-arg by design — APScheduler stores
# job callables in its jobstore by qualified name, so we cannot capture
# the DB engine or HTTP client in a closure that's safe across restarts.
# They build their own session + EdgarClient per run and own their
# commit boundary.


async def daily_pro_refresh_entrypoint() -> None:  # pragma: no cover - thin wiring
    """Open session + EdgarClient, run daily Pro refresh, commit."""
    from app.database import async_session

    try:
        async with async_session() as db, EdgarClient() as edgar:
            try:
                result = await daily_pro_refresh(db, edgar)
                await db.commit()
                logger.info("13f_pro_daily_complete", **result)
            except Exception as exc:
                await db.rollback()
                logger.exception("13f_pro_daily_failed", error=str(exc))
    except Exception as exc:
        # Last-resort guard: never let APScheduler see an exception —
        # if we did, the misfire policy would re-schedule us into a
        # tighter loop and burn the EDGAR rate budget.
        logger.exception("13f_pro_daily_outer_failed", error=str(exc))


async def weekly_basic_refresh_entrypoint() -> None:  # pragma: no cover - thin wiring
    """Open session + EdgarClient, run weekly Basic refresh, commit."""
    from app.database import async_session

    try:
        async with async_session() as db, EdgarClient() as edgar:
            try:
                result = await weekly_basic_refresh(db, edgar)
                await db.commit()
                logger.info("13f_basic_weekly_complete", **result)
            except Exception as exc:
                await db.rollback()
                logger.exception("13f_basic_weekly_failed", error=str(exc))
    except Exception as exc:
        logger.exception("13f_basic_weekly_outer_failed", error=str(exc))
