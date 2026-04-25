"""APScheduler-based automatic sync scheduler.

Runs daily after market close and periodic catch-up syncs.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.modules.sync_manager.scheduler import SyncScheduler

logger = structlog.get_logger()


class AutoSyncScheduler:
    """Automatic sync scheduler -- runs daily after TWSE market close."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
        self._sync = SyncScheduler()
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Register jobs and start the APScheduler loop."""
        # Daily full sync at 17:30 Taipei time (after market close)
        self._scheduler.add_job(
            self._daily_sync,
            CronTrigger(hour=17, minute=30, timezone="Asia/Taipei"),
            id="daily_sync",
            name="每日資料同步",
            replace_existing=True,
        )

        # Catch-up sync every 2 hours (handles rate-limit interrupted runs)
        self._scheduler.add_job(
            self._catchup_sync,
            CronTrigger(hour="*/2", minute=0, timezone="Asia/Taipei"),
            id="catchup_sync",
            name="補同步",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        logger.info("auto_scheduler_started", jobs=self.get_jobs())

    def stop(self) -> None:
        """Shutdown the APScheduler loop."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("auto_scheduler_stopped")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def get_jobs(self) -> list[dict]:
        """Return a summary of all scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
            }
            for job in self._scheduler.get_jobs()
        ]

    # ------------------------------------------------------------------
    # Job implementations
    # ------------------------------------------------------------------

    async def _daily_sync(self) -> None:
        """Full sync triggered by the daily schedule."""
        logger.info("auto_sync_daily_start")
        from app.database import async_session

        async with async_session() as db:
            await self._sync.run_all_with_notify(db)

    async def _catchup_sync(self) -> None:
        """Catch-up sync -- only runs prices (the most quota-intensive task)."""
        logger.info("auto_sync_catchup_start")
        from app.database import async_session

        async with async_session() as db:
            result = await self._sync.run_task("prices", db, batch_size=100)
            if result.records_synced > 0:
                await self._sync._notify(
                    f"\U0001f504 補同步完成: {result.records_synced} 筆股價 ({result.stocks_processed} 支)"
                )
