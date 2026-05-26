"""Unit tests for StockInfoSyncTask."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.industry import Industry
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.stock_info import StockInfoSyncTask


def _record(
    stock_id: str = "2330",
    stock_name: str = "TSMC",
    industry: str = "Semiconductor",
    type_: str = "twse",
) -> dict[str, Any]:
    return {
        "stock_id": stock_id,
        "stock_name": stock_name,
        "industry_category": industry,
        "type": type_,
    }


async def test_run_inserts_new_stocks_and_industries(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("2330", "TSMC", "Semiconductor", "twse"),
        _record("3008", "Largan", "Optoelectronics", "OTC"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.dataset == "stock_info"
    assert result.stopped_reason == "completed"
    assert result.records_synced == 2

    stocks = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    assert [s.symbol for s in stocks] == ["2330.TW", "3008.TW"]
    # OTC should map to TW_TPEX, others TW_TWSE
    by_symbol = {s.symbol: s for s in stocks}
    assert by_symbol["2330.TW"].market == Market.TW_TWSE
    assert by_symbol["3008.TW"].market == Market.TW_TPEX

    industries = (await db_session.execute(select(Industry))).scalars().all()
    assert {i.name for i in industries} == {"Semiconductor", "Optoelectronics"}

    state = (await db_session.execute(select(SyncState))).scalar_one()
    assert state.dataset == "stock_info"
    assert state.stock_id is None
    assert state.records_synced == 2


async def test_run_skips_records_missing_id_or_name(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        {"stock_id": "", "stock_name": "X", "type": "twse", "industry_category": "A"},
        {"stock_id": "1234", "stock_name": "", "type": "twse", "industry_category": "A"},
        _record("2330", "TSMC", "Semi", "twse"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.records_synced == 1


async def test_run_reuses_existing_industry(db_session: AsyncSession) -> None:
    existing = Industry(name="Semiconductor")
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(
            return_value=[_record("2330", "TSMC", "Semiconductor", "twse")]
        )
        await task.run(db_session, rl)

    industries = (await db_session.execute(select(Industry))).scalars().all()
    assert len(industries) == 1
    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.industry_id == existing.id


async def test_run_handles_empty_industry_name(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(
            return_value=[_record("2330", "TSMC", "", "twse")]
        )
        await task.run(db_session, rl)

    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.industry_id is None


async def test_run_upserts_existing_stock(db_session: AsyncSession) -> None:
    db_session.add(Stock(symbol="2330.TW", name="OldName", market=Market.TW_TWSE))
    await db_session.commit()

    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(
            return_value=[_record("2330", "NewName", "Semi", "twse")]
        )
        await task.run(db_session, rl)

    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.name == "NewName"


async def test_run_returns_rate_limit_when_acquire_fails(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch.object(rl, "wait_and_acquire", AsyncMock(return_value=False)):
        result = await task.run(db_session, rl)
    assert result.stopped_reason == "rate_limit"


async def test_run_handles_provider_error(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(side_effect=RuntimeError("nope"))
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "error"
    assert result.errors == 1
    assert "nope" in result.error_details[0]


async def test_run_updates_existing_sync_state_row(db_session: AsyncSession) -> None:
    db_session.add(
        SyncState(
            dataset="stock_info",
            stock_id=None,
            last_synced_date=None,
            last_run_at=datetime.now(UTC),
            status="idle",
            records_synced=0,
            error_message="old error",
        )
    )
    await db_session.commit()

    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(
            return_value=[_record("2330", "TSMC", "Semi", "twse")]
        )
        result = await task.run(db_session, rl)

    assert result.records_synced == 1
    states = (await db_session.execute(select(SyncState))).scalars().all()
    assert len(states) == 1
    assert states[0].status == "completed"
    assert states[0].error_message is None
