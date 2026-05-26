"""Unit tests for MarginSyncTask."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.margin import MarginTrading
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindRateLimitError
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.margin import MarginSyncTask


def _raw_margin(d: str = "2024-01-02") -> dict[str, Any]:
    return {
        "date": d,
        "MarginPurchaseBuy": 1000,
        "MarginPurchaseSell": 800,
        "MarginPurchaseCashRepayment": 200,
        "MarginPurchaseLimit": 9999,
        "ShortSaleBuy": 50,
        "ShortSaleSell": 70,
        "ShortSaleCashRepayment": 20,
        "ShortSaleLimit": 5000,
        "OffsetLoanAndShort": 5,
    }


async def _add_stock(db: AsyncSession, symbol: str = "2330.TW") -> Stock:
    stock = Stock(symbol=symbol, name="TestCo", market=Market.TW_TWSE)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock


async def test_run_no_active_stocks(db_session: AsyncSession) -> None:
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    result = await task.run(db_session, rl)

    assert result.dataset == "margin"
    assert result.stopped_reason == "completed"
    assert result.stocks_processed == 0


async def test_run_skip_already_up_to_date(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    # Match production: today computed in Asia/Taipei (see sync_manager/tasks/margin.py).
    today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
    db_session.add(
        SyncState(
            dataset="margin",
            stock_id=stock.id,
            last_synced_date=today,
            last_run_at=datetime.now(UTC),
            status="completed",
            records_synced=1,
            error_message=None,
        )
    )
    await db_session.commit()

    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=[])
        result = await task.run(db_session, rl)

    assert result.stocks_processed == 0
    client_cls.return_value.fetch.assert_not_awaited()


async def test_run_inserts_margin_rows(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    raw = [_raw_margin("2024-01-02"), _raw_margin("2024-01-03")]
    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.records_synced == 2
    assert result.stopped_reason == "completed"
    rows = (await db_session.execute(select(MarginTrading))).scalars().all()
    assert len(rows) == 2
    row = rows[0]
    assert row.margin_buy == 1000
    assert row.short_sell == 70

    state = (await db_session.execute(select(SyncState))).scalar_one()
    assert state.stock_id == stock.id
    assert state.last_synced_date == date(2024, 1, 3)


async def test_run_resumes_from_last_synced(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    db_session.add(
        SyncState(
            dataset="margin",
            stock_id=stock.id,
            last_synced_date=date(2024, 1, 1),
            last_run_at=datetime.now(UTC),
            status="completed",
            records_synced=0,
            error_message=None,
        )
    )
    await db_session.commit()

    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        fetch = AsyncMock(return_value=[_raw_margin("2024-01-02")])
        client_cls.return_value.fetch = fetch
        await task.run(db_session, rl)

    kwargs = fetch.call_args.kwargs
    assert kwargs["start_date"] == (date(2024, 1, 1) + timedelta(days=1)).isoformat()


async def test_run_skips_invalid_row(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    raw = [{"date": "INVALID"}, _raw_margin("2024-01-02")]
    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.records_synced == 1


async def test_run_fetch_error_recorded(db_session: AsyncSession) -> None:
    await _add_stock(db_session, symbol="2330.TW")
    await _add_stock(db_session, symbol="2317.TW")
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(
            side_effect=[RuntimeError("boom"), [_raw_margin("2024-01-02")]]
        )
        result = await task.run(db_session, rl)

    assert result.errors == 1
    assert result.records_synced == 1


async def test_run_breaks_on_rate_limit_error(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=FinMindRateLimitError())
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_breaks_when_rate_limiter_returns_false(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch.object(rl, "wait_and_acquire", AsyncMock(return_value=False)):
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_breaks_at_batch_when_remaining_low(db_session: AsyncSession) -> None:
    await _add_stock(db_session, symbol="2330.TW")
    await _add_stock(db_session, symbol="2317.TW")
    task = MarginSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with (
        patch("app.modules.sync_manager.tasks.margin.FinMindClient") as client_cls,
        patch.object(type(rl), "remaining", new=4),
    ):
        client_cls.return_value.fetch = AsyncMock(return_value=[_raw_margin("2024-01-02")])
        result = await task.run(db_session, rl, batch_size=1)

    assert result.stopped_reason == "rate_limit"
    assert result.stocks_processed == 1
