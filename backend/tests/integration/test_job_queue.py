"""Integration tests for BacktestJobQueue async DB operations.

Exercises every public method: enqueue / claim_next / update_progress /
complete / fail / cancel / get_queue_status / get_history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_result import BacktestResultRecord
from app.services.job_queue import BacktestJobQueue

# ── enqueue / claim_next ──────────────────────────────────────────────────


async def test_enqueue_creates_pending_job(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(
        db_session, config={"strategy": "ma_crossover"}, symbol="2330", job_type="single"
    )
    await db_session.commit()
    assert job.id is not None
    assert job.symbol == "2330"
    assert job.status == "pending"
    assert job.job_type == "single"


async def test_claim_next_returns_none_when_empty(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.claim_next(db_session)
    assert job is None


async def test_claim_next_picks_highest_priority(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    await q.enqueue(db_session, {}, "A", "single", priority=0)
    high = await q.enqueue(db_session, {}, "B", "single", priority=10)
    await db_session.commit()

    claimed = await q.claim_next(db_session)
    assert claimed is not None
    assert claimed.id == high.id
    assert claimed.status == "running"


# ── update_progress / complete / fail ─────────────────────────────────────


async def test_update_progress(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    await q.update_progress(db_session, job.id, pct=50)
    await db_session.refresh(job)
    assert job.progress_pct == 50


async def test_update_progress_caps_at_100(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    await q.update_progress(db_session, job.id, pct=150)
    await db_session.refresh(job)
    assert job.progress_pct == 100


async def test_complete_sets_status_and_result(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    await q.complete(db_session, job.id, {"return": 0.15})
    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.progress_pct == 100
    assert job.result_json == {"return": 0.15}


async def test_fail_sets_status_and_error(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    await q.fail(db_session, job.id, error="boom!")
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_message == "boom!"


async def test_fail_truncates_long_error(db_session: AsyncSession) -> None:
    """Error message > 1000 chars is truncated to 1000."""
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    long_err = "x" * 5000
    await q.fail(db_session, job.id, error=long_err)
    await db_session.refresh(job)
    assert len(job.error_message) == 1000


# ── cancel ────────────────────────────────────────────────────────────────


async def test_cancel_pending_returns_true(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()

    ok = await q.cancel(db_session, job.id)
    assert ok is True
    await db_session.refresh(job)
    assert job.status == "cancelled"


async def test_cancel_running_returns_false(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    job.status = "running"
    await db_session.commit()

    ok = await q.cancel(db_session, job.id)
    assert ok is False
    await db_session.refresh(job)
    assert job.status == "running"  # unchanged


async def test_cancel_missing_returns_false(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    ok = await q.cancel(db_session, 99999)
    assert ok is False


# ── get_queue_status ──────────────────────────────────────────────────────


async def test_queue_status_returns_pending_and_running_only(
    db_session: AsyncSession,
) -> None:
    q = BacktestJobQueue()
    j1 = await q.enqueue(db_session, {}, "A", "single")
    j2 = await q.enqueue(db_session, {}, "B", "single")
    j3 = await q.enqueue(db_session, {}, "C", "single")
    j2.status = "running"
    j3.status = "completed"
    await db_session.commit()

    jobs = await q.get_queue_status(db_session)
    ids = {j.id for j in jobs}
    assert j1.id in ids  # pending
    assert j2.id in ids  # running
    assert j3.id not in ids  # completed excluded


async def test_queue_status_user_filter(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    a = await q.enqueue(db_session, {}, "A", "single", user_id=1)
    b = await q.enqueue(db_session, {}, "B", "single", user_id=2)
    await db_session.commit()

    jobs = await q.get_queue_status(db_session, user_id=1)
    ids = {j.id for j in jobs}
    assert a.id in ids
    assert b.id not in ids


# ── get_history ───────────────────────────────────────────────────────────


async def test_history_empty_returns_empty(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    out = await q.get_history(db_session)
    assert out == []


async def test_history_returns_results_ordered_by_return(
    db_session: AsyncSession,
) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()
    # Seed 3 result rows with varying total_return
    for ret in [0.10, 0.30, 0.20]:
        rec = BacktestResultRecord(
            job_id=job.id,
            symbol="2330",
            strategy_name="ma_crossover",
            strategy_params={},
            metrics_json={},
            equity_curve=[],
            trade_log=[],
            total_return=ret,
            sharpe_ratio=1.0,
            win_rate=0.5,
        )
        db_session.add(rec)
    await db_session.commit()

    out = await q.get_history(db_session)
    returns = [r.total_return for r in out]
    assert returns == sorted(returns, reverse=True)


async def test_history_pagination(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "2330", "single")
    await db_session.commit()
    for i in range(5):
        db_session.add(
            BacktestResultRecord(
                job_id=job.id,
                symbol="2330",
                strategy_name="s",
                strategy_params={},
                metrics_json={},
                equity_curve=[],
                trade_log=[],
                total_return=0.1 + i * 0.01,
                sharpe_ratio=1.0,
                win_rate=0.5,
            )
        )
    await db_session.commit()

    out = await q.get_history(db_session, limit=2, offset=1)
    assert len(out) == 2


async def test_history_symbol_filter(db_session: AsyncSession) -> None:
    q = BacktestJobQueue()
    job = await q.enqueue(db_session, {}, "X", "single")
    await db_session.commit()
    for sym in ["2330", "0050", "2330"]:
        db_session.add(
            BacktestResultRecord(
                job_id=job.id,
                symbol=sym,
                strategy_name="s",
                strategy_params={},
                metrics_json={},
                equity_curve=[],
                trade_log=[],
                total_return=0.1,
                sharpe_ratio=1.0,
                win_rate=0.5,
            )
        )
    await db_session.commit()

    out = await q.get_history(db_session, symbol="2330")
    assert len(out) == 2
    assert all(r.symbol == "2330" for r in out)
