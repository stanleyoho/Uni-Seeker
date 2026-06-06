"""APScheduler-based automatic sync scheduler.

Runs daily after market close and periodic catch-up syncs.
"""

from __future__ import annotations

from typing import Any

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
        """Register jobs and start the APScheduler loop.

        Every job is registered with ``max_instances=1`` and
        ``coalesce=True``. A full sync can run for many minutes (rate-limited
        FinMind pulls across thousands of symbols); without ``max_instances=1``
        APScheduler's default of 1 still applies, but we set it *explicitly*
        so a slow run is guaranteed never to stack a second concurrent
        invocation of the same job on top of itself (which would double the
        upstream rate-budget consumption and race on ``sync_states`` rows).
        ``coalesce=True`` collapses multiple missed fire-times — e.g. after a
        deploy/restart window — into a single catch-up run instead of a burst.
        """
        # Daily full sync at 17:30 Taipei time (after market close)
        self._scheduler.add_job(
            self._daily_sync,
            CronTrigger(hour=17, minute=30, timezone="Asia/Taipei"),
            id="daily_sync",
            name="每日資料同步",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # TW 三大法人 dedicated post-close pull at 17:35 — TWSE publishes
        # at ~17:00, so we wait 30 min for upstream to settle then run
        # *just* this task. Reason it's separate from daily_sync: if the
        # earlier tasks (prices/financials) eat the FinMind rate budget,
        # institutional flow STILL needs to land tonight so the morning
        # pre-market signal board has fresh chip data. Two independent
        # runs = two independent rate-budget evaluations.
        self._scheduler.add_job(
            self._tw_institutional_sync,
            CronTrigger(hour=17, minute=35, timezone="Asia/Taipei"),
            id="tw_institutional_postclose",
            name="三大法人盤後同步",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Catch-up sync every 2 hours (handles rate-limit interrupted runs)
        self._scheduler.add_job(
            self._catchup_sync,
            CronTrigger(hour="*/2", minute=0, timezone="Asia/Taipei"),
            id="catchup_sync",
            name="補同步",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # ETF estimated NAV refresh at 17:35 Taipei — runs 5 min after
        # the main daily sync so the stocks/prices side has settled by
        # the time we resolve ETF symbols against `stocks.name LIKE
        # '%ETF%'`. Powers /api/v1/etf-arbitrage/list.
        self._scheduler.add_job(
            self._etf_nav_sync,
            CronTrigger(hour=17, minute=35, timezone="Asia/Taipei"),
            id="etf_nav_sync",
            name="ETF 預估淨值同步",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # 四大買賣點 (Best Four Buy/Sell Points) daily scan at 17:40 Taipei —
        # runs 10 min after the main daily sync so the day's TW prices have
        # landed before we compute MA3/MA6 + volume points across the whole
        # TW universe and persist today's snapshot into ``signal_scans``.
        # ``max_instances=1`` so a slow universe scan never stacks; the scan
        # is idempotent per scan_date (delete-then-insert) so ``coalesce``
        # collapsing a missed fire into one catch-up run is safe.
        self._scheduler.add_job(
            self._best_four_point_scan,
            CronTrigger(hour=17, minute=40, timezone="Asia/Taipei"),
            id="best_four_point_scan",
            name="四大買賣點掃描",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
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

    def get_jobs(self) -> list[dict[str, Any]]:
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

    async def _tw_institutional_sync(self) -> None:
        """Dedicated post-close 三大法人 sync — independent rate budget.

        ``run_task`` already writes status + bumps Prometheus counter on
        failure; the broad try/except here is belt-and-suspenders so an
        outer crash still emits a log line instead of vanishing into the
        APScheduler executor's exception swallow.
        """
        logger.info("auto_sync_tw_institutional_start")
        from app.database import async_session

        async with async_session() as db:
            try:
                result = await self._sync.run_task("tw_institutional", db)
                logger.info(
                    "auto_sync_tw_institutional_finished",
                    records=result.records_synced,
                    stocks=result.stocks_processed,
                    stopped=result.stopped_reason,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "auto_sync_tw_institutional_exception",
                    error=str(exc),
                )

    async def _catchup_sync(self) -> None:
        """Catch-up sync -- runs all tasks to handle rate-limit interrupted runs."""
        import time
        from datetime import datetime
        from zoneinfo import ZoneInfo

        logger.info("auto_sync_catchup_start")
        from app.database import async_session

        started_at = time.monotonic()
        async with async_session() as db:
            results = await self._sync.run_all(db, batch_size=100)
        elapsed_s = time.monotonic() - started_at

        total = sum(r.records_synced for r in results)
        if total == 0:
            return

        # Per-dataset breakdown, sorted by records desc; mark rate-limit / error.
        ts = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%H:%M")
        lines: list[str] = [f"\U0001f504 補同步完成 ({ts}, {elapsed_s:.0f}s)"]
        sorted_results = sorted(results, key=lambda r: r.records_synced, reverse=True)
        for r in sorted_results:
            if r.records_synced == 0 and r.stopped_reason in (None, "completed"):
                continue  # skip silent no-op tasks
            mark = {"rate_limit": " ⚠️", "error": " ❌"}.get(r.stopped_reason or "", "")
            lines.append(f"  · {r.dataset}: {r.records_synced} 筆 / {r.stocks_processed} 檔{mark}")
            # Surface per-task breakdown when present
            if r.details:
                non_zero = [(k, v) for k, v in r.details.items() if v]
                if non_zero:
                    body = " · ".join(f"{k} {v}" for k, v in non_zero)
                    lines.append(f"      {body}")
            for label, examples in r.extras.items():
                if examples:
                    lines.append(f"      {label}: {', '.join(examples)}")
        lines.append(f"\U0001f4c8 合計: {total} 筆 across {len(results)} 任務")
        await self._sync._notify("\n".join(lines))

    async def _etf_nav_sync(self) -> None:
        """Refresh ETF estimated NAV for the premium/discount monitor.

        Best-effort: NAV is an *enrichment* for the arbitrage view, not
        a primary financial record. If FinMind rate-limits or the
        dataset isn't available for the current token tier we log and
        move on — the endpoint already degrades gracefully with a
        ``message`` field.
        """
        logger.info("auto_sync_etf_nav_start")
        from datetime import date, timedelta

        from sqlalchemy import select

        from app.database import async_session
        from app.models.enums import Market
        from app.models.stock import Stock
        from app.modules.finmind.market_provider import FinMindMarketProvider

        provider = FinMindMarketProvider()
        async with async_session() as db:
            result = await db.execute(
                select(Stock)
                .where(Stock.market.in_((Market.TW_TWSE, Market.TW_TPEX)))
                .where(Stock.is_active.is_(True))
                .where(Stock.name.like("%ETF%"))
            )
            etfs = list(result.scalars().all())

        start = (date.today() - timedelta(days=7)).isoformat()
        ok = 0
        for etf in etfs:
            symbol_id = etf.symbol.replace(".TW", "").replace(".TWO", "")
            try:
                raw = await provider.fetch_etf_nav(stock_id=symbol_id, start_date=start)
            except Exception as exc:
                logger.warning("etf_nav_sync_skip", symbol=symbol_id, error=str(exc))
                continue
            if raw:
                ok += 1
        logger.info("auto_sync_etf_nav_done", refreshed=ok, total=len(etfs))

    async def _best_four_point_scan(self) -> None:
        """Daily 四大買賣點 universe scan — persists today's snapshot.

        Owns its own session + commit boundary (the service commits once at
        the end). Best-effort: a failure logs and returns instead of
        propagating to the APScheduler executor, so a bad scan night never
        re-schedules itself into a tight retry loop.
        """
        logger.info("auto_best_four_point_scan_start")
        from app.database import async_session
        from app.services.best_four_point import run_best_four_point_scan

        async with async_session() as db:
            try:
                summary = await run_best_four_point_scan(db)
                logger.info("auto_best_four_point_scan_finished", **summary)
            except Exception as exc:  # pragma: no cover - defensive
                await db.rollback()
                logger.error("auto_best_four_point_scan_exception", error=str(exc))
