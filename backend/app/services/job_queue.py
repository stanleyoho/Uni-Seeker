from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord
from app.obs.logging import get_logger

logger = get_logger(component="job_queue")


class BacktestJobQueue:
    """PostgreSQL-backed job queue using FOR UPDATE SKIP LOCKED for concurrency-safe claiming."""

    async def enqueue(
        self,
        db: AsyncSession,
        config: dict[str, Any],
        symbol: str,
        job_type: str,
        user_id: int | None = None,
        priority: int = 0,
    ) -> BacktestJob:
        """Create a new backtest job and add it to the queue."""
        job = BacktestJob(
            symbol=symbol,
            job_type=job_type,
            user_id=user_id,
            priority=priority,
            config_json=config,
        )
        db.add(job)
        await db.flush()
        logger.info("Enqueued backtest job id=%s symbol=%s type=%s", job.id, symbol, job_type)
        return job

    async def claim_next(self, db: AsyncSession) -> BacktestJob | None:
        """Atomically claim the highest-priority pending job.

        Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple workers can
        poll concurrently without contention or double-processing.
        """
        stmt = (
            select(BacktestJob)
            .where(BacktestJob.status == "pending")
            .order_by(BacktestJob.priority.desc(), BacktestJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.status = "running"
        job.started_at = datetime.now(UTC)
        await db.flush()
        logger.info("Claimed backtest job id=%s", job.id)
        return job

    async def update_progress(self, db: AsyncSession, job_id: int, pct: int) -> None:
        """Update the progress percentage for a running job."""
        stmt = (
            update(BacktestJob).where(BacktestJob.id == job_id).values(progress_pct=min(pct, 100))
        )
        await db.execute(stmt)
        await db.flush()

    async def complete(self, db: AsyncSession, job_id: int, result: dict[str, Any]) -> None:
        """Mark a job as completed with its result payload."""
        now = datetime.now(UTC)
        stmt = (
            update(BacktestJob)
            .where(BacktestJob.id == job_id)
            .values(
                status="completed",
                result_json=result,
                progress_pct=100,
                completed_at=now,
            )
        )
        await db.execute(stmt)
        await db.flush()
        logger.info("Completed backtest job id=%s", job_id)

    async def fail(self, db: AsyncSession, job_id: int, error: str) -> None:
        """Mark a job as failed with an error message."""
        now = datetime.now(UTC)
        stmt = (
            update(BacktestJob)
            .where(BacktestJob.id == job_id)
            .values(
                status="failed",
                error_message=error[:1000],
                completed_at=now,
            )
        )
        await db.execute(stmt)
        await db.flush()
        logger.warning("Failed backtest job id=%s error=%s", job_id, error[:200])

    async def cancel(self, db: AsyncSession, job_id: int) -> bool:
        """Cancel a pending job. Returns True if cancellation succeeded.

        Only jobs in 'pending' status can be cancelled. Running jobs
        should be stopped via the worker's cancellation mechanism.
        """
        stmt = (
            update(BacktestJob)
            .where(BacktestJob.id == job_id, BacktestJob.status == "pending")
            .values(
                status="cancelled",
                completed_at=datetime.now(UTC),
            )
        )
        result = await db.execute(stmt)
        await db.flush()
        cancelled = bool(result.rowcount > 0)
        if cancelled:
            logger.info("Cancelled backtest job id=%s", job_id)
        return cancelled

    async def get_queue_status(
        self,
        db: AsyncSession,
        user_id: int | None = None,
    ) -> list[BacktestJob]:
        """Return pending and running jobs, optionally filtered by user."""
        stmt = (
            select(BacktestJob)
            .where(BacktestJob.status.in_(["pending", "running"]))
            .order_by(BacktestJob.priority.desc(), BacktestJob.created_at.asc())
        )
        if user_id is not None:
            stmt = stmt.where(BacktestJob.user_id == user_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_history(
        self,
        db: AsyncSession,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BacktestResultRecord]:
        """Return completed backtest results, optionally filtered by symbol."""
        stmt = (
            select(BacktestResultRecord)
            .where(BacktestResultRecord.deleted_at.is_(None))
            .order_by(BacktestResultRecord.total_return.desc())
            .limit(limit)
            .offset(offset)
        )
        if symbol is not None:
            stmt = stmt.where(BacktestResultRecord.symbol == symbol)
        result = await db.execute(stmt)
        return list(result.scalars().all())
