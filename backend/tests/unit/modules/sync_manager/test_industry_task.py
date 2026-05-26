"""Unit tests for IndustryAggregatesSyncTask."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.financial_metrics import FinancialMetrics
from app.models.stock import Stock
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.industry import IndustryAggregatesSyncTask


async def _add_metric(db: AsyncSession, period: str = "2024-Q1") -> None:
    stock = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    db.add(FinancialMetrics(stock_id=stock.id, period=period, fiscal_year=2024, fiscal_quarter=1))
    await db.commit()


async def test_run_returns_completed_when_no_period_found(db_session: AsyncSession) -> None:
    task = IndustryAggregatesSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    result = await task.run(db_session, rl)

    assert result.dataset == "industry_aggregates"
    assert result.stopped_reason == "completed"
    assert result.records_synced == 0


async def test_run_invokes_aggregator_with_latest_period(db_session: AsyncSession) -> None:
    await _add_metric(db_session, period="2024-Q1")

    task = IndustryAggregatesSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.industry.IndustryAggregator") as agg_cls:
        agg = agg_cls.return_value
        agg.aggregate_all_industries = AsyncMock(return_value=None)
        result = await task.run(db_session, rl)

    agg.aggregate_all_industries.assert_awaited_once_with("2024-Q1")
    assert result.records_synced == 1
    assert result.stopped_reason == "completed"


async def test_run_picks_latest_period_when_multiple(db_session: AsyncSession) -> None:
    stock = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
    db_session.add(stock)
    await db_session.commit()
    await db_session.refresh(stock)
    for period, q in [("2024-Q1", 1), ("2024-Q3", 3), ("2024-Q2", 2)]:
        db_session.add(
            FinancialMetrics(stock_id=stock.id, period=period, fiscal_year=2024, fiscal_quarter=q)
        )
    await db_session.commit()

    task = IndustryAggregatesSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.industry.IndustryAggregator") as agg_cls:
        agg = agg_cls.return_value
        agg.aggregate_all_industries = AsyncMock(return_value=None)
        await task.run(db_session, rl)

    # lexicographic max of 2024-Q1, 2024-Q2, 2024-Q3 → "2024-Q3"
    agg.aggregate_all_industries.assert_awaited_once_with("2024-Q3")


async def test_run_catches_aggregator_error(db_session: AsyncSession) -> None:
    await _add_metric(db_session, period="2024-Q1")

    task = IndustryAggregatesSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.industry.IndustryAggregator") as agg_cls:
        agg = agg_cls.return_value
        agg.aggregate_all_industries = AsyncMock(side_effect=RuntimeError("boom"))
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "error"
    assert result.errors == 1
    assert "boom" in result.error_details[0]
    assert result.records_synced == 0
