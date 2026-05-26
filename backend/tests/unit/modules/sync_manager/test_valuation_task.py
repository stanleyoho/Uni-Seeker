"""Unit tests for ValuationSyncTask and run_valuation_sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.stock import Stock
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.valuation import (
    ValuationSyncTask,
    run_valuation_sync,
)


async def _add_stocks(db: AsyncSession, n: int = 2, *, active: bool = True) -> list[Stock]:
    stocks = []
    for i in range(n):
        s = Stock(
            symbol=f"233{i}.TW",
            name=f"Co{i}",
            market=Market.TW_TWSE,
            is_active=active,
        )
        db.add(s)
        stocks.append(s)
    await db.commit()
    for s in stocks:
        await db.refresh(s)
    return stocks


async def test_run_valuation_sync_no_stocks(db_session: AsyncSession) -> None:
    out = await run_valuation_sync(db_session, limit=10)
    assert out == {"total_processed": 0, "success": 0, "errors": 0}


async def test_run_valuation_sync_counts_success_and_errors(
    db_session: AsyncSession,
) -> None:
    await _add_stocks(db_session, n=3)

    with patch("app.modules.sync_manager.tasks.valuation.CompositeEstimator") as estimator_cls:
        estimator = estimator_cls.return_value
        # 1st succeeds (truthy), 2nd returns None (no success), 3rd raises
        estimator.calculate_and_save = AsyncMock(side_effect=[object(), None, RuntimeError("boom")])
        out = await run_valuation_sync(db_session, limit=10)

    assert out["total_processed"] == 3
    assert out["success"] == 1
    assert out["errors"] == 1


async def test_run_valuation_sync_only_active_stocks(db_session: AsyncSession) -> None:
    await _add_stocks(db_session, n=2)
    inactive = Stock(symbol="9999.TW", name="Dead", market=Market.TW_TWSE, is_active=False)
    db_session.add(inactive)
    await db_session.commit()

    with patch("app.modules.sync_manager.tasks.valuation.CompositeEstimator") as estimator_cls:
        estimator_cls.return_value.calculate_and_save = AsyncMock(return_value=object())
        out = await run_valuation_sync(db_session, limit=10)

    assert out["total_processed"] == 2


async def test_run_valuation_sync_respects_limit(db_session: AsyncSession) -> None:
    await _add_stocks(db_session, n=5)
    with patch("app.modules.sync_manager.tasks.valuation.CompositeEstimator") as estimator_cls:
        estimator_cls.return_value.calculate_and_save = AsyncMock(return_value=object())
        out = await run_valuation_sync(db_session, limit=2)

    assert out["total_processed"] == 2
    assert out["success"] == 2


async def test_valuation_task_returns_sync_result(db_session: AsyncSession) -> None:
    await _add_stocks(db_session, n=2)
    task = ValuationSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.valuation.CompositeEstimator") as estimator_cls:
        estimator_cls.return_value.calculate_and_save = AsyncMock(
            side_effect=[object(), RuntimeError("x")]
        )
        result = await task.run(db_session, rl, batch_size=100)

    assert result.dataset == "valuation"
    assert result.stocks_processed == 2
    assert result.records_synced == 1
    assert result.errors == 1
    assert result.stopped_reason == "completed"
