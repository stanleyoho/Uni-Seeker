"""Backend cron-style job scheduler — 13F refresh jobs.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2 (refresh policy) + Q1 (Pro daily / Basic weekly / Free on-demand only).

This package owns the *13F-tier-driven* APScheduler instance. It is
distinct from ``app.modules.sync_manager.auto_scheduler.AutoSyncScheduler``
(daily TWSE close + 2h catch-up sync), because:

- Time zone differs (UTC vs ``Asia/Taipei``) — combining them into one
  scheduler would force one of the cron triggers to think in the
  wrong wall clock.
- Job ownership differs — TWSE sync is owned by ``sync_manager``;
  13F refresh is owned by ``services.institutional``. Keeping two
  schedulers preserves a clean blast-radius boundary: a bug in the
  TWSE sync run loop cannot crash the 13F job loop or vice versa.

Public surface:

- ``get_scheduler()``       — accessor for the singleton ``AsyncIOScheduler``.
- ``register_jobs(s)``      — wires up the cron triggers (idempotent).
- ``lifespan_scheduler()``  — ``asynccontextmanager`` for FastAPI lifespan
                              integration. Start on enter / shutdown on
                              exit / replaces existing jobs on each enter.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


logger = structlog.get_logger(__name__)


# Module-level singleton. Lifespan + tests both touch the same instance
# so a smoke test can inspect ``get_scheduler().get_jobs()`` after the
# lifespan context entered.
_scheduler: AsyncIOScheduler | None = None


JOB_ID_PRO_DAILY = "13f_pro_daily"
JOB_ID_BASIC_WEEKLY = "13f_basic_weekly"
JOB_ID_ALERTS_PRO_HOURLY = "alerts_pro_hourly"
JOB_ID_ALERTS_BASIC_SIX_HOURLY = "alerts_basic_six_hourly"


def get_scheduler() -> AsyncIOScheduler:
    """Return (and lazily construct) the singleton scheduler.

    Constructed with ``timezone='UTC'`` because both 13F cron triggers
    are UTC-anchored — 06:00 UTC sits comfortably after the US filing
    window closes (see ``scheduled_refresh_job`` docstring).
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the 13F cron jobs on ``scheduler``.

    Idempotent: ``replace_existing=True`` means re-running this on the
    same scheduler instance (as the lifespan context will on a hot
    reload) wipes + re-registers without raising ``ConflictingIdError``.

    ``max_instances=1`` prevents two simultaneous Pro-daily runs from
    overlapping if a previous run took >24h (it shouldn't, but safety
    first — the global EDGAR rate budget cannot tolerate doubling up).
    ``misfire_grace_time=3600`` lets a delayed worker still pick up a
    missed fire within 1 hour rather than silently dropping it.
    """
    # Import here to break the import cycle:
    #   main.py -> scheduler -> services.institutional.scheduled_refresh_job
    #            -> services.institutional.filing_service
    #            -> ... -> app.repositories.institutional -> app.models
    # and main.py also -> app.api -> services.institutional. By deferring
    # the import to registration time we let main.py finish import-time
    # wiring first.
    from app.services.institutional.scheduled_refresh_job import (
        daily_pro_refresh_entrypoint,
        weekly_basic_refresh_entrypoint,
    )

    scheduler.add_job(
        daily_pro_refresh_entrypoint,
        CronTrigger(hour=6, minute=0),
        id=JOB_ID_PRO_DAILY,
        name="13F Pro daily refresh (06:00 UTC)",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )

    scheduler.add_job(
        weekly_basic_refresh_entrypoint,
        CronTrigger(day_of_week="sun", hour=6, minute=0),
        id=JOB_ID_BASIC_WEEKLY,
        name="13F Basic weekly refresh (Sun 06:00 UTC)",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # ── Alert-rule scheduled evaluation (UNI-ALERT-001) ───────────────────
    # Pro: every hour on the hour. Basic: every 6h. Free: not scheduled
    # (max_alert_rules=0 → no rules to evaluate). Both jobs share the
    # same misfire grace (1h) as the 13F crons so a brief downtime does
    # not silently drop a cycle.
    from app.services.alerts.scheduled_alert_evaluator import (
        hourly_pro_alert_entrypoint,
        six_hour_basic_alert_entrypoint,
    )

    scheduler.add_job(
        hourly_pro_alert_entrypoint,
        CronTrigger(minute=0),
        id=JOB_ID_ALERTS_PRO_HOURLY,
        name="Alerts Pro hourly evaluation",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )

    scheduler.add_job(
        six_hour_basic_alert_entrypoint,
        CronTrigger(hour="0,6,12,18", minute=0),
        id=JOB_ID_ALERTS_BASIC_SIX_HOURLY,
        name="Alerts Basic 6-hourly evaluation",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )


@asynccontextmanager
async def lifespan_scheduler() -> AsyncIterator[AsyncIOScheduler]:
    """FastAPI-lifespan-friendly start/stop of the 13F scheduler.

    Use as ``async with lifespan_scheduler():`` inside the main app
    lifespan. The yielded scheduler is the same instance you can
    introspect via ``get_scheduler()``.

    Shutdown uses ``wait=False`` so the FastAPI shutdown sequence isn't
    blocked waiting for an in-flight refresh — APScheduler's own job
    cancellation will surface the partial state via the job's own
    rollback logic inside ``*_entrypoint``.
    """
    scheduler = get_scheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info(
        "13f_scheduler_started",
        jobs=[j.id for j in scheduler.get_jobs()],
    )
    try:
        yield scheduler
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("13f_scheduler_stopped")


__all__ = [
    "JOB_ID_ALERTS_BASIC_SIX_HOURLY",
    "JOB_ID_ALERTS_PRO_HOURLY",
    "JOB_ID_BASIC_WEEKLY",
    "JOB_ID_PRO_DAILY",
    "get_scheduler",
    "lifespan_scheduler",
    "register_jobs",
]
