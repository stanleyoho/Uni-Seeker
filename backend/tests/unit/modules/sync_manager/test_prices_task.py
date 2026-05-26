"""Unit tests for PriceSyncTask."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindRateLimitError
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.prices import PriceSyncTask


def _raw_price(d: str = "2024-01-02", close: float = 105.0, spread: float = 5.0) -> dict[str, Any]:
    return {
        "date": d,
        "open": 100.0,
        "max": 110.0,
        "min": 99.0,
        "close": close,
        "Trading_Volume": 1_000_000,
        "spread": spread,
    }


async def _add_stock(db: AsyncSession, symbol: str = "2330.TW") -> Stock:
    stock = Stock(symbol=symbol, name="TestCo", market=Market.TW_TWSE)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock


async def test_run_no_active_stocks_returns_completed(db_session: AsyncSession) -> None:
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    result = await task.run(db_session, rl)

    assert result.dataset == "prices"
    assert result.stopped_reason == "completed"
    assert result.stocks_processed == 0


async def test_run_skips_stock_when_already_up_to_date(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    today = datetime.now().date()
    db_session.add(
        SyncState(
            dataset="prices",
            stock_id=stock.id,
            last_synced_date=today,
            last_run_at=datetime.now(UTC),
            status="completed",
            records_synced=0,
            error_message=None,
        )
    )
    await db_session.commit()

    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=[])
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "completed"
    assert result.stocks_processed == 0
    client_cls.return_value.fetch.assert_not_awaited()


async def test_run_inserts_prices_and_updates_sync_state(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    raw = [_raw_price("2024-01-02"), _raw_price("2024-01-03", close=108.0)]
    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "completed"
    assert result.records_synced == 2
    assert result.stocks_processed == 1

    rows = (await db_session.execute(select(StockPrice))).scalars().all()
    assert len(rows) == 2

    state = (await db_session.execute(select(SyncState))).scalar_one()
    assert state.dataset == "prices"
    assert state.stock_id == stock.id
    assert state.last_synced_date == date(2024, 1, 3)


async def test_run_resumes_from_last_synced_date(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    db_session.add(
        SyncState(
            dataset="prices",
            stock_id=stock.id,
            last_synced_date=date(2024, 1, 1),
            last_run_at=datetime.now(UTC),
            status="completed",
            records_synced=1,
            error_message=None,
        )
    )
    await db_session.commit()

    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        fetch = AsyncMock(return_value=[_raw_price("2024-01-02")])
        client_cls.return_value.fetch = fetch
        await task.run(db_session, rl)

    fetch.assert_awaited_once()
    kwargs = fetch.call_args.kwargs
    # Should resume from last_synced + 1 day
    assert kwargs["start_date"] == (date(2024, 1, 1) + timedelta(days=1)).isoformat()
    assert kwargs["data_id"] == "2330"  # .TW stripped


async def test_run_skips_invalid_rows(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    raw = [
        {"date": "BAD", "open": 1, "max": 1, "min": 1, "close": 1, "Trading_Volume": 1},
        _raw_price("2024-01-02"),
    ]
    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.records_synced == 1


async def test_run_records_fetch_error_and_continues(db_session: AsyncSession) -> None:
    await _add_stock(db_session, symbol="2330.TW")
    await _add_stock(db_session, symbol="2317.TW")
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(
            side_effect=[RuntimeError("boom"), [_raw_price("2024-01-02")]]
        )
        result = await task.run(db_session, rl)

    assert result.errors == 1
    assert result.records_synced == 1
    assert "boom" in result.error_details[0]


async def test_run_breaks_on_rate_limit_error(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=FinMindRateLimitError())
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_breaks_when_rate_limiter_exhausted(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch.object(rl, "wait_and_acquire", AsyncMock(return_value=False)):
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_breaks_at_batch_when_remaining_low(db_session: AsyncSession) -> None:
    # Two stocks, batch_size=1, then rate_limiter.remaining will drop below 5
    await _add_stock(db_session, symbol="2330.TW")
    await _add_stock(db_session, symbol="2317.TW")
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with (
        patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls,
        patch.object(type(rl), "remaining", new=4),
    ):
        client_cls.return_value.fetch = AsyncMock(return_value=[_raw_price("2024-01-02")])
        result = await task.run(db_session, rl, batch_size=1)

    assert result.stopped_reason == "rate_limit"
    assert result.stocks_processed == 1


@pytest.mark.parametrize("change,prev_close_expected", [(5.0, 100.0), (0.0, None)])
async def test_run_change_percent_computation(
    db_session: AsyncSession, change: float, prev_close_expected: float | None
) -> None:
    """Cover the prev_close branch in change_percent computation."""
    await _add_stock(db_session)
    task = PriceSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    raw = [_raw_price("2024-01-02", close=105.0, spread=change)]
    with patch("app.modules.sync_manager.tasks.prices.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        await task.run(db_session, rl)

    row = (await db_session.execute(select(StockPrice))).scalar_one()
    if prev_close_expected is None:
        assert row.change_percent == 0
    else:
        assert row.change_percent > 0
