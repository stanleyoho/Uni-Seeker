"""Backtest job queue and history API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord
from app.schemas.backtest_job import (
    BacktestHistoryItem,
    BacktestHistoryResponse,
    JobEnqueueRequest,
    JobResultResponse,
    JobStatusResponse,
    QueueStatusResponse,
)
from app.services.job_queue import BacktestJobQueue

router = APIRouter(prefix="/backtest", tags=["backtest-jobs"])

_queue = BacktestJobQueue()


def _job_to_response(job: BacktestJob) -> JobStatusResponse:
    """Convert a BacktestJob ORM instance to the API response schema."""
    return JobStatusResponse(
        id=job.id,
        symbol=job.symbol,
        job_type=job.job_type,
        status=job.status,
        progress_pct=job.progress_pct,
        created_at=job.created_at.isoformat() if job.created_at else "",
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message,
    )


def _result_to_history_item(rec: BacktestResultRecord) -> BacktestHistoryItem:
    """Convert a BacktestResultRecord ORM instance to the history item schema."""
    metrics = rec.metrics_json or {}
    trade_log = None
    # `rec.trade_log` is typed `list[...] | dict[...]` (union accommodates
    # legacy {} placeholder rows) — only the list shape carries entries.
    if isinstance(rec.trade_log, list) and rec.trade_log:
        from app.schemas.backtest_job import TradeLogEntry

        trade_log = [
            TradeLogEntry(
                date=t.get("date", ""),
                action=t.get("action", ""),
                price=t.get("price", 0),
                shares=t.get("shares", 0),
                reason=t.get("reason", ""),
            )
            for t in rec.trade_log
        ]
    # equity_curve can be a list or dict with a "curve" key
    raw_curve = rec.equity_curve
    equity_list: list[float] | None = None
    if isinstance(raw_curve, list):
        equity_list = raw_curve
    elif isinstance(raw_curve, dict) and "curve" in raw_curve:
        equity_list = raw_curve["curve"]

    return BacktestHistoryItem(
        id=rec.id,
        job_id=rec.job_id,
        symbol=rec.symbol,
        strategy_name=rec.strategy_name,
        strategy_params=rec.strategy_params or {},
        total_return=rec.total_return,
        annualized_return=metrics.get("annualized_return", 0.0),
        max_drawdown=metrics.get("max_drawdown", 0.0),
        sharpe_ratio=rec.sharpe_ratio,
        win_rate=rec.win_rate,
        total_trades=metrics.get("total_trades", 0),
        profit_factor=metrics.get("profit_factor", 0.0),
        trade_log=trade_log,
        equity_curve=equity_list,
        backtest_type=rec.backtest_type or "single",
        composite_mode=rec.composite_mode,
        date_range_start=rec.date_range_start.isoformat() if rec.date_range_start else None,
        date_range_end=rec.date_range_end.isoformat() if rec.date_range_end else None,
        buy_hold_return=rec.buy_hold_return,
        trading_days=rec.trading_days,
        created_at=rec.created_at.isoformat() if rec.created_at else "",
    )


@router.post("/jobs", response_model=JobStatusResponse, status_code=201)
async def enqueue_job(
    req: JobEnqueueRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobStatusResponse:
    """Enqueue a new backtest job."""
    config = {
        "symbol": req.symbol,
        "job_type": req.job_type,
        "strategy": req.strategy,
        "strategies": req.strategies,
        "mode": req.mode,
        "params": req.params,
        "strategy_params": req.strategy_params,
        "param_grid": req.param_grid,
        "initial_capital": req.initial_capital,
        "position_size": req.position_size,
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit,
    }

    job = await _queue.enqueue(
        db=db,
        config=config,
        symbol=req.symbol,
        job_type=req.job_type,
    )
    await db.commit()
    return _job_to_response(job)


@router.get("/jobs", response_model=QueueStatusResponse)
async def get_queue_status(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueueStatusResponse:
    """Get current queue status with all pending and running jobs."""
    jobs = await _queue.get_queue_status(db)

    running_count = sum(1 for j in jobs if j.status == "running")
    pending_count = sum(1 for j in jobs if j.status == "pending")

    return QueueStatusResponse(
        jobs=[_job_to_response(j) for j in jobs],
        running_count=running_count,
        pending_count=pending_count,
    )


@router.get("/jobs/{job_id}", response_model=JobResultResponse)
async def get_job_result(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResultResponse:
    """Get a single job and its associated backtest results."""
    stmt = select(BacktestJob).where(BacktestJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    results_stmt = (
        select(BacktestResultRecord)
        .where(BacktestResultRecord.job_id == job_id)
        .order_by(BacktestResultRecord.total_return.desc())
    )
    results = await db.execute(results_stmt)
    records = list(results.scalars().all())

    return JobResultResponse(
        job=_job_to_response(job),
        results=[_result_to_history_item(r) for r in records],
    )


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Cancel a pending job. Only pending jobs can be cancelled."""
    cancelled = await _queue.cancel(db, job_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} cannot be cancelled (not in pending status or not found)",
        )
    await db.commit()


@router.get("/history", response_model=BacktestHistoryResponse)
async def get_backtest_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    symbol: str | None = Query(default=None, description="Filter by stock symbol"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BacktestHistoryResponse:
    """Get paginated backtest result history, optionally filtered by symbol."""
    # Count total matching records
    count_stmt = select(func.count(BacktestResultRecord.id))
    if symbol is not None:
        count_stmt = count_stmt.where(BacktestResultRecord.symbol == symbol)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Fetch paginated results
    records = await _queue.get_history(db, symbol=symbol, limit=limit, offset=offset)

    return BacktestHistoryResponse(
        results=[_result_to_history_item(r) for r in records],
        total=total,
    )


@router.get("/results/{result_id}", response_model=BacktestHistoryItem)
async def get_result_by_id(
    result_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BacktestHistoryItem:
    """Get a single backtest result by ID."""
    stmt = select(BacktestResultRecord).where(BacktestResultRecord.id == result_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Result {result_id} not found")
    return _result_to_history_item(record)


@router.get("/history/{symbol}/best", response_model=list[BacktestHistoryItem])
async def get_best_results_for_symbol(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BacktestHistoryItem]:
    """Get the top 10 best backtest results for a symbol, sorted by total return."""
    stmt = (
        select(BacktestResultRecord)
        .where(BacktestResultRecord.symbol == symbol)
        .order_by(BacktestResultRecord.total_return.desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    records = list(result.scalars().all())

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest results found for symbol '{symbol}'",
        )

    return [_result_to_history_item(r) for r in records]
