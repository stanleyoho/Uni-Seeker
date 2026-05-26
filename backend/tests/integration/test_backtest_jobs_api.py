"""Integration tests for /api/v1/backtest/* job queue + history endpoints.

Covers the seven public endpoints in `app.api.v1.backtest_jobs`:
- POST   /jobs               enqueue
- GET    /jobs               queue status
- GET    /jobs/{id}          job + results lookup
- DELETE /jobs/{id}          cancel pending
- GET    /history            paginated history
- GET    /results/{id}       single result
- GET    /history/{symbol}/best   top-10 by return

Endpoints don't require auth; tests use the shared `client` fixture +
`db_session` to seed BacktestJob / BacktestResultRecord rows directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord


async def _mk_job(
    db: AsyncSession,
    symbol: str = "2330",
    status: str = "pending",
    job_type: str = "single",
) -> BacktestJob:
    job = BacktestJob(
        symbol=symbol,
        job_type=job_type,
        config_json={"strategy": "ma_crossover"},
    )
    job.status = status
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _mk_result(
    db: AsyncSession,
    job_id: int,
    symbol: str = "2330",
    strategy_name: str = "ma_crossover",
    total_return: float = 0.15,
) -> BacktestResultRecord:
    rec = BacktestResultRecord(
        job_id=job_id,
        symbol=symbol,
        strategy_name=strategy_name,
        strategy_params={"period": 20},
        metrics_json={"sharpe_ratio": 1.5},
        equity_curve=[100.0, 105.0, 115.0],
        trade_log=[
            {"date": "2026-04-01", "action": "BUY", "price": 580, "shares": 100, "reason": "entry"}
        ],
        total_return=total_return,
        sharpe_ratio=1.5,
        win_rate=0.6,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


# ── POST /jobs (enqueue) ──────────────────────────────────────────────────


async def test_enqueue_single_job_returns_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = {
        "symbol": "2330",
        "job_type": "single",
        "strategy": "ma_crossover",
        "strategy_params": {"ma_crossover": {"period": 20}},
        "params": {"days": 365},
        "initial_capital": 100000,
    }
    resp = await client.post("/api/v1/backtest/jobs", json=body)
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["symbol"] == "2330"
    assert data["job_type"] == "single"
    assert data["status"] == "pending"


# ── GET /jobs (queue status) ──────────────────────────────────────────────


async def test_queue_status_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/backtest/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running_count"] == 0
    assert data["pending_count"] == 0
    assert data["jobs"] == []


async def test_queue_status_counts_by_status(client: AsyncClient, db_session: AsyncSession) -> None:
    await _mk_job(db_session, "2330", status="pending")
    await _mk_job(db_session, "0050", status="pending")
    await _mk_job(db_session, "2317", status="running")

    resp = await client.get("/api/v1/backtest/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_count"] == 2
    assert data["running_count"] == 1


# ── GET /jobs/{id} ────────────────────────────────────────────────────────


async def test_get_job_result_404_when_missing(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/backtest/jobs/9999")
    assert resp.status_code == 404


async def test_get_job_result_returns_results_ordered_by_return(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _mk_job(db_session, "2330")
    # Insert in non-sorted order
    await _mk_result(db_session, job.id, strategy_name="strategyB", total_return=0.20)
    await _mk_result(db_session, job.id, strategy_name="strategyA", total_return=0.30)
    await _mk_result(db_session, job.id, strategy_name="strategyC", total_return=0.10)

    resp = await client.get(f"/api/v1/backtest/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job"]["id"] == job.id
    returns = [r["total_return"] for r in data["results"]]
    assert returns == sorted(returns, reverse=True)


# ── DELETE /jobs/{id} (cancel) ────────────────────────────────────────────


async def test_cancel_pending_job_returns_204(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _mk_job(db_session, "2330", status="pending")
    resp = await client.delete(f"/api/v1/backtest/jobs/{job.id}")
    assert resp.status_code == 204


async def test_cancel_running_job_returns_409(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _mk_job(db_session, "2330", status="running")
    resp = await client.delete(f"/api/v1/backtest/jobs/{job.id}")
    assert resp.status_code == 409


async def test_cancel_missing_job_returns_409(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/backtest/jobs/9999")
    assert resp.status_code == 409


# ── GET /history (paginated) ──────────────────────────────────────────────


async def test_history_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/backtest/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


async def test_history_returns_results_with_total(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _mk_job(db_session, "2330")
    await _mk_result(db_session, job.id, total_return=0.1)
    await _mk_result(db_session, job.id, total_return=0.2)

    resp = await client.get("/api/v1/backtest/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["results"]) == 2


async def test_history_filter_by_symbol(client: AsyncClient, db_session: AsyncSession) -> None:
    job = await _mk_job(db_session, "2330")
    await _mk_result(db_session, job.id, symbol="2330")
    await _mk_result(db_session, job.id, symbol="0050")

    resp = await client.get("/api/v1/backtest/history?symbol=0050")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["symbol"] == "0050"


async def test_history_pagination_respected(client: AsyncClient, db_session: AsyncSession) -> None:
    job = await _mk_job(db_session, "2330")
    for i in range(5):
        await _mk_result(db_session, job.id, total_return=0.1 + i * 0.01)

    resp = await client.get("/api/v1/backtest/history?limit=2&offset=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["results"]) == 2


# ── GET /results/{id} ─────────────────────────────────────────────────────


async def test_get_result_by_id(client: AsyncClient, db_session: AsyncSession) -> None:
    job = await _mk_job(db_session, "2330")
    rec = await _mk_result(db_session, job.id, total_return=0.25)

    resp = await client.get(f"/api/v1/backtest/results/{rec.id}")
    assert resp.status_code == 200
    assert resp.json()["total_return"] == 0.25


async def test_get_result_by_id_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/backtest/results/9999")
    assert resp.status_code == 404


# ── GET /history/{symbol}/best ────────────────────────────────────────────


async def test_best_for_symbol_returns_top10(client: AsyncClient, db_session: AsyncSession) -> None:
    job = await _mk_job(db_session, "2330")
    for i in range(12):
        await _mk_result(db_session, job.id, symbol="2330", total_return=0.01 * i)

    resp = await client.get("/api/v1/backtest/history/2330/best")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 10
    # Should be sorted DESC
    returns = [r["total_return"] for r in items]
    assert returns == sorted(returns, reverse=True)


async def test_best_for_unknown_symbol_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/backtest/history/UNKNOWN/best")
    assert resp.status_code == 404
