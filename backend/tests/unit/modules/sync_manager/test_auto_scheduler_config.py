"""B6a — AutoSyncScheduler job-registration hardening.

Regression guard: every job registered by ``AutoSyncScheduler.start`` must
carry ``max_instances=1`` and ``coalesce=True`` so a slow sync (rate-limited
FinMind pulls can run for many minutes) can never stack a second concurrent
invocation of the same job on top of itself, and a backlog of missed
fire-times (e.g. across a deploy/restart) collapses into a single catch-up
run instead of a burst.
"""

from __future__ import annotations

import pytest

from app.modules.sync_manager.auto_scheduler import AutoSyncScheduler

_EXPECTED_JOB_IDS = {
    "daily_sync",
    "tw_institutional_postclose",
    "catchup_sync",
    "etf_nav_sync",
    "best_four_point_scan",
}


@pytest.fixture
async def started_scheduler() -> AutoSyncScheduler:
    """Start a scheduler, yield it, and always shut it down.

    ``AsyncIOScheduler.start()`` calls ``asyncio.get_running_loop()``, so the
    fixture is async to guarantee a live loop is present when jobs are
    registered.
    """
    sched = AutoSyncScheduler()
    sched.start()
    try:
        yield sched
    finally:
        sched.stop()


async def test_all_expected_jobs_registered(started_scheduler: AutoSyncScheduler) -> None:
    job_ids = {job.id for job in started_scheduler._scheduler.get_jobs()}
    assert job_ids == _EXPECTED_JOB_IDS


async def test_every_job_has_max_instances_one(started_scheduler: AutoSyncScheduler) -> None:
    """No job may overlap itself — a long run must not stack."""
    for job in started_scheduler._scheduler.get_jobs():
        assert job.max_instances == 1, f"{job.id} allows overlapping runs"


async def test_every_job_coalesces_missed_runs(started_scheduler: AutoSyncScheduler) -> None:
    """Missed fire-times collapse into one catch-up run, not a burst."""
    for job in started_scheduler._scheduler.get_jobs():
        assert job.coalesce is True, f"{job.id} does not coalesce missed runs"
