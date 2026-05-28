"""Unit tests for SyncScheduler.run_task error-handling path.

Regression coverage for the 2026-04-30 silent-fail incident:
``margin`` / ``revenue`` / ``per_pbr`` sync tasks recorded
``status=partial, records=0, error_message=None`` for 27 days because the
scheduler's except block could not write the error_message column (the
underlying partial unique index was missing — PR #88 fixed that). These
tests enforce the post-incident invariant: ANY exception from a sync task
MUST populate ``sync_states.error_message`` AND increment the
``uni_sync_task_failures_total`` Prometheus counter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_state import SyncState
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.scheduler import SyncScheduler
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask
from app.obs.metrics import SYNC_TASK_FAILURES_TOTAL


class _BoomTask(SyncTask):
    """SyncTask that always raises — simulates a real-world crash mid-sync."""

    dataset_name = "stock_info"  # reuse an already-registered slot

    async def run(  # type: ignore[override]
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        raise ValueError("simulated upstream failure")


async def _counter_value(task: str, error_type: str) -> float:
    """Read the current value of the labelled counter (0.0 if never inc'd)."""
    return SYNC_TASK_FAILURES_TOTAL.labels(task=task, error_type=error_type)._value.get()


@pytest.mark.asyncio
async def test_run_task_exception_writes_error_message_and_increments_counter(
    db_session: AsyncSession,
) -> None:
    """Crash path MUST persist error_message AND bump the failures counter."""
    scheduler = SyncScheduler()
    # Replace the registered task with one that raises. Keeping the same key
    # ("stock_info") avoids touching scheduler internals or task ordering.
    scheduler._tasks["stock_info"] = _BoomTask()  # type: ignore[assignment]

    before = await _counter_value("stock_info", "ValueError")

    result = await scheduler.run_task("stock_info", db_session, batch_size=50)

    # Result shape: scheduler returns an error-summary SyncResult, never re-raises.
    assert result.stopped_reason == "error"
    assert result.errors == 1
    assert "ValueError" in result.error_details[0]

    # Invariant 1: error_message is populated (non-None, contains class name).
    q = await db_session.execute(
        select(SyncState).where(
            SyncState.dataset == "stock_info",
            SyncState.stock_id.is_(None),
        )
    )
    row = q.scalar_one()
    assert row.status == "failed", (
        "exception path must use status='failed' (not 'partial'/'error') so "
        "operators can distinguish crash vs rate-limit vs clean-no-rows"
    )
    assert row.error_message is not None, "silent-fail regression: error_message empty"
    assert "ValueError" in row.error_message, (
        f"error_message must include the exception class name; got {row.error_message!r}"
    )

    # Invariant 2: Prometheus counter incremented exactly once.
    after = await _counter_value("stock_info", "ValueError")
    assert after == before + 1, (
        f"sync_task_failures_total{{task=stock_info,error_type=ValueError}} "
        f"expected +1, got {after - before}"
    )


@pytest.mark.asyncio
async def test_run_task_exception_status_write_failure_still_increments_counter(
    db_session: AsyncSession,
) -> None:
    """Even if ``_set_global_status`` itself raises (the exact 4/30 root cause),
    the counter MUST still increment so the failure is visible in metrics.
    """
    scheduler = SyncScheduler()
    scheduler._tasks["stock_info"] = _BoomTask()  # type: ignore[assignment]

    # Sabotage the status writer to simulate the missing-partial-index regime.
    # We bypass the "running" status write (first call succeeds) and only fail
    # the second call (the error-path write) — emulating the real 4/30 timing
    # where the first INSERT worked but ON CONFLICT on a non-existent index
    # blew up the second update.
    call_count = {"n": 0}
    original = scheduler._set_global_status

    async def flaky_set_status(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await original(*args, **kwargs)
        raise RuntimeError("simulated InFailedSQLTransactionError")

    scheduler._set_global_status = AsyncMock(side_effect=flaky_set_status)  # type: ignore[method-assign]

    before = await _counter_value("stock_info", "ValueError")

    # Must NOT raise — the scheduler swallows the secondary write failure
    # (it's already logged loudly) so the caller still gets a SyncResult.
    result = await scheduler.run_task("stock_info", db_session, batch_size=50)

    assert result.stopped_reason == "error"
    after = await _counter_value("stock_info", "ValueError")
    assert after == before + 1, (
        "counter must increment BEFORE the status write so observability "
        "survives DB-level write failures (the 4/30 mechanism)"
    )
