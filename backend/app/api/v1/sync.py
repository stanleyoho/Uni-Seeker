"""API endpoints for data synchronisation management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.sync_manager.scheduler import SyncScheduler

router = APIRouter(prefix="/sync", tags=["sync"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# A single scheduler instance shared across requests so the rate limiter
# state is preserved for the lifetime of the process.
_scheduler = SyncScheduler()


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class SyncTaskResult(BaseModel):
    dataset: str
    stocks_processed: int
    records_synced: int
    errors: int
    stopped_reason: str | None = None
    error_details: list[str] = []


class SyncStatusItem(BaseModel):
    dataset: str
    status: str
    last_synced_date: str | None = None
    last_run_at: str | None = None
    records_synced: int = 0
    error_message: str | None = None


class RateLimiterStatus(BaseModel):
    remaining: int
    max_requests: int


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/run/{task_name}", response_model=SyncTaskResult)
async def run_sync_task(
    task_name: str,
    db: DbSession,
    background_tasks: BackgroundTasks,
    batch_size: int = 50,
) -> SyncTaskResult:
    """Trigger a single sync task by name.

    Valid task names: ``stock_info``, ``prices``, ``margin``, ``per_pbr``.
    """
    if task_name not in _scheduler.task_names:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task_name}'. Valid: {_scheduler.task_names}",
        )

    result = await _scheduler.run_task(task_name, db, batch_size)
    return SyncTaskResult(
        dataset=result.dataset,
        stocks_processed=result.stocks_processed,
        records_synced=result.records_synced,
        errors=result.errors,
        stopped_reason=result.stopped_reason,
        error_details=result.error_details,
    )


@router.post("/run-all", response_model=list[SyncTaskResult])
async def run_all_sync(
    db: DbSession,
    batch_size: int = 50,
) -> list[SyncTaskResult]:
    """Execute all sync tasks in order: stock_info -> prices -> margin -> per_pbr.

    Stops early if the API rate limit is reached.
    Sends a Telegram notification on completion if configured.
    """
    results = await _scheduler.run_all_with_notify(db, batch_size)
    return [
        SyncTaskResult(
            dataset=r.dataset,
            stocks_processed=r.stocks_processed,
            records_synced=r.records_synced,
            errors=r.errors,
            stopped_reason=r.stopped_reason,
            error_details=r.error_details,
        )
        for r in results
    ]


@router.get("/status", response_model=list[SyncStatusItem])
async def get_sync_status(db: DbSession) -> list[SyncStatusItem]:
    """Return the current synchronisation state for every dataset."""
    rows = await _scheduler.get_status(db)
    return [SyncStatusItem(**row) for row in rows]


@router.get("/rate-limit", response_model=RateLimiterStatus)
async def get_rate_limit_status() -> RateLimiterStatus:
    """Return the current state of the shared rate limiter."""
    return RateLimiterStatus(
        remaining=_scheduler.rate_limiter.remaining,
        max_requests=550,
    )


class SchedulerJobInfo(BaseModel):
    id: str
    name: str
    next_run: str | None = None


class SchedulerStatus(BaseModel):
    running: bool
    jobs: list[SchedulerJobInfo]


@router.get("/scheduler", response_model=SchedulerStatus)
async def get_scheduler_status() -> SchedulerStatus:
    """Return the current state of the automatic sync scheduler."""
    from app.main import auto_scheduler

    return SchedulerStatus(
        running=auto_scheduler.is_running,
        jobs=[SchedulerJobInfo(**j) for j in auto_scheduler.get_jobs()],
    )
