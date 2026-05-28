"""Sync task: 13F institutional filings (SEC EDGAR).

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2 + §9 (tier-driven refresh cadence) + §11 R3 (EDGAR fair-use).

Wraps the existing ``scheduled_refresh_job.refresh_for_tier`` so the
``sync_manager`` surface (and its ``POST /api/v1/sync/run/{task_name}``
endpoint) can drive the same per-tier 13F refresh that APScheduler runs
on its 06:00 UTC cron. This is the only sync task that talks to SEC
EDGAR rather than FinMind, so it bypasses the shared FinMind
``RateLimiter`` and relies on ``EdgarClient``'s own token-bucket
limiter (10 req/sec, SEC policy) instead.

Why we loop tiers here instead of taking ``tier`` as input:
``SyncScheduler.run_task`` invokes tasks by string name only. Surfacing
two tasks (``f13_pro`` + ``f13_basic``) would duplicate registration for
no operational benefit — the per-tier *skip windows* already make a
combined run idempotent (Pro filers refreshed within 12h are skipped,
Basic filers within 6 days are skipped). FREE tier is rejected upstream
by ``refresh_for_tier`` and we never call it for FREE.

Anti-coupling:
- Does NOT touch the SyncTask base class (Axis Q parallel work).
- Does NOT modify ``F13FilingService`` / ``EdgarClient`` / scheduled_refresh_job.
- Adds zero alembic migrations — schema already in place.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import UserTier
from app.modules.institutional.edgar_client import EdgarClient
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask
from app.services.institutional.scheduled_refresh_job import (
    daily_pro_refresh,
    weekly_basic_refresh,
)

logger = structlog.get_logger(__name__)


# Tiers we sync in this task, in execution order. FREE is excluded by
# spec Q1 (on-demand only). We run PRO first because its 12h skip window
# means it's almost always the lighter call.
_TIERS_TO_SYNC: tuple[UserTier, ...] = (UserTier.PRO, UserTier.BASIC)


class F13FilingsSyncTask(SyncTask):
    """Synchronise 13F institutional filings for all subscribed filers.

    Per-tier cadence (delegated to ``scheduled_refresh_job``):
      PRO   — 12h skip window
      BASIC — 6-day skip window
      FREE  — never auto-refreshed (rejected upstream)

    Records counted as ``records_synced`` are *new filings ingested*
    (not holdings) so the dashboard's per-task counter aligns with the
    user-facing notion of "new 13F filings landed this run." Holdings
    counts are still logged for operator visibility.
    """

    dataset_name = "f13_filings"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        # ``rate_limiter`` is the shared FinMind limiter. EDGAR has its
        # own SEC-policy token bucket inside ``EdgarClient`` so we do
        # NOT consume FinMind permits here — the parameter is part of
        # the ``SyncTask`` contract and intentionally unused.
        del rate_limiter, batch_size

        result = SyncResult(dataset=self.dataset_name)

        # Open a single EdgarClient for the whole run so the per-tier
        # loops share one token bucket + one HTTP connection pool. The
        # client is required by SEC policy to ship a contact-bearing UA;
        # ``settings.sec_edgar_user_agent`` defaults to the same value
        # ``EdgarClient`` hard-codes, but operators can override via
        # ``UNI_SEC_EDGAR_USER_AGENT``.
        try:
            async with EdgarClient(user_agent=settings.sec_edgar_user_agent) as edgar:
                for tier in _TIERS_TO_SYNC:
                    await self._sync_tier(db, edgar, tier, result)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception(
                "f13_filings_sync_unexpected_error",
                dataset=self.dataset_name,
                error=str(exc),
            )
            result.errors += 1
            result.error_details.append(f"unexpected: {exc}")
            result.stopped_reason = "error"
            return result

        if result.stopped_reason is None:
            result.stopped_reason = "completed"

        logger.info(
            "f13_filings_sync_finished",
            dataset=self.dataset_name,
            stocks_processed=result.stocks_processed,
            records_synced=result.records_synced,
            errors=result.errors,
            stopped=result.stopped_reason,
        )
        return result

    async def _sync_tier(
        self,
        db: AsyncSession,
        edgar: EdgarClient,
        tier: UserTier,
        result: SyncResult,
    ) -> None:
        """Run the per-tier refresh job and fold its stats into ``result``.

        Failures inside ``refresh_for_tier`` are already classified into
        the returned ``errors`` counter; an *outer* exception (which
        would only happen on a programming bug or DB outage) is logged +
        counted but does NOT abort the other tiers — losing one tier on
        a transient failure shouldn't take the other down too.
        """
        try:
            if tier is UserTier.PRO:
                stats = await daily_pro_refresh(db, edgar)
            elif tier is UserTier.BASIC:
                stats = await weekly_basic_refresh(db, edgar)
            else:
                # Defensive: _TIERS_TO_SYNC currently only has PRO+BASIC
                # but if a future edit adds FREE we want a clean log
                # rather than an opaque ValueError from refresh_for_tier.
                logger.warning(
                    "f13_filings_sync_skipped_unsupported_tier",
                    dataset=self.dataset_name,
                    tier=tier.value,
                )
                return
        except Exception as exc:
            logger.exception(
                "f13_filings_sync_tier_error",
                dataset=self.dataset_name,
                tier=tier.value,
                error=str(exc),
            )
            result.errors += 1
            result.error_details.append(f"{tier.value}: {exc}")
            return

        # ``stats["filers_refreshed"]`` → stocks_processed analogue
        # (one filer == one "thing we processed").
        # ``stats["filings_added"]``    → records_synced (the new rows).
        result.stocks_processed += int(stats.get("filers_refreshed", 0))
        result.records_synced += int(stats.get("filings_added", 0))
        result.errors += int(stats.get("errors", 0))

        logger.info(
            "f13_filings_sync_tier_finished",
            dataset=self.dataset_name,
            tier=tier.value,
            users_processed=stats.get("users_processed", 0),
            filers_refreshed=stats.get("filers_refreshed", 0),
            filings_added=stats.get("filings_added", 0),
            holdings_added=stats.get("holdings_added", 0),
            skipped=stats.get("skipped", 0),
            errors=stats.get("errors", 0),
        )
