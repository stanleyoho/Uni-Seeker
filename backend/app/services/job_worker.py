from __future__ import annotations

import asyncio
import logging

from app.database import async_session
from app.models.backtest_job import BacktestJob
from app.services.job_queue import BacktestJobQueue

logger = logging.getLogger(__name__)

# Interval in seconds between queue polls when idle.
_POLL_INTERVAL = 2.0


class BacktestJobWorker:
    """Background worker that polls the job queue and executes backtest jobs.

    Usage::

        worker = BacktestJobWorker()
        await worker.start()   # spawns the polling loop as a background task
        ...
        await worker.stop()    # graceful shutdown
    """

    def __init__(self) -> None:
        self._queue = BacktestJobQueue()
        self._task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._task is not None:
            logger.warning("BacktestJobWorker is already running")
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._poll_loop(), name="backtest-worker")
        logger.info("BacktestJobWorker started")

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        if self._task is None:
            return
        self._shutdown.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("BacktestJobWorker stopped")

    async def _poll_loop(self) -> None:
        """Continuously claim and execute jobs until shutdown is signalled."""
        logger.info("BacktestJobWorker poll loop running")
        while not self._shutdown.is_set():
            try:
                async with async_session() as db:
                    job = await self._queue.claim_next(db)
                    if job is not None:
                        await self._execute_job(job, db)
                        await db.commit()
                    else:
                        await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in BacktestJobWorker poll loop")

            # Wait before next poll; break early on shutdown signal.
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=_POLL_INTERVAL,
                )
                break  # shutdown was signalled
            except asyncio.TimeoutError:
                pass  # normal — continue polling

    async def _execute_job(self, job: BacktestJob, db: "AsyncSession") -> None:  # noqa: F821
        """Dispatch job to the appropriate backtest engine.

        This is a placeholder implementation. The actual engine integration
        (single strategy, composite, grid search, portfolio) will be wired
        in Wave 2.
        """
        from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession  # noqa: F811

        assert isinstance(db, _AsyncSession)

        logger.info(
            "Executing job id=%s type=%s symbol=%s",
            job.id, job.job_type, job.symbol,
        )

        try:
            await self._queue.update_progress(db, job.id, 10)

            # --- Placeholder: dispatch based on job_type ---
            # In Wave 2 this will call the real backtest engines:
            #   single     -> SingleStrategyEngine
            #   composite  -> CompositeStrategyEngine
            #   grid_search -> GridSearchEngine
            #   portfolio  -> PortfolioEngine
            placeholder_result = {
                "engine": "placeholder",
                "job_type": job.job_type,
                "symbol": job.symbol,
                "message": "Backtest engine not yet integrated — placeholder result.",
            }

            await self._queue.update_progress(db, job.id, 90)
            await self._queue.complete(db, job.id, result=placeholder_result)

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            await self._queue.fail(db, job.id, error_msg)
