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
    date: str = "2026-06-21",
) -> dict[str, Any]:
    return {
        "stock_id": stock_id,
        "stock_name": stock_name,
        "industry_category": industry,
        "type": type_,
        "date": date,
    }


async def test_run_inserts_new_stocks_and_industries(db_session: AsyncSession) -> None:
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("2330", "TSMC", "Semiconductor", "twse"),
        _record("3008", "Largan", "Optoelectronics", "tpex"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.dataset == "stock_info"
    assert result.stopped_reason == "completed"
    assert result.records_synced == 2

    stocks = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    # twse → ".TW", tpex → ".TWO" (NOT ".TW" for everything as before)
    assert [s.symbol for s in stocks] == ["2330.TW", "3008.TWO"]
    by_symbol = {s.symbol: s for s in stocks}
    assert by_symbol["2330.TW"].market == Market.TW_TWSE
    assert by_symbol["3008.TWO"].market == Market.TW_TPEX

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


# --------------------------------------------------------------------------
# Real-bug-shape tests: type→market mapping, dedup, idempotency.
# --------------------------------------------------------------------------


async def test_type_mapping_twse_tpex_emerging(db_session: AsyncSession) -> None:
    """twse→.TW/TW_TWSE, tpex→.TWO/TW_TPEX, emerging is skipped (no enum value)."""
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("2330", "TSMC", "Semiconductor", "twse"),
        _record("3008", "Largan", "Optoelectronics", "tpex"),
        _record("6173", "信昌電", "Electronics", "emerging"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    # emerging is skipped, not written.
    assert result.records_synced == 2
    assert result.details["略過興櫃"] == 1

    stocks = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    by_symbol = {s.symbol: s for s in stocks}
    assert set(by_symbol) == {"2330.TW", "3008.TWO"}
    assert by_symbol["2330.TW"].market == Market.TW_TWSE
    assert by_symbol["3008.TWO"].market == Market.TW_TPEX
    # The emerging stock_id never produced a row under any suffix.
    assert "6173.TW" not in by_symbol
    assert "6173.TWO" not in by_symbol


async def test_duplicate_stock_id_newest_date_wins(db_session: AsyncSession) -> None:
    """5450 appears twice (寶聯通 2020 stale, 南良 2026 current), both tpex.

    The newest-date record (南良) must win under ONE symbol; the stale
    寶聯通 must NOT win and must NOT trigger a phantom rename.
    """
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    # Order the stale record AFTER the current one to prove dedup is by
    # date, not by feed order (the reverted fix was order-dependent).
    raw = [
        _record("5450", "南良", "Textiles", "tpex", date="2026-06-21"),
        _record("5450", "寶聯通", "Other", "tpex", date="2020-06-03"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    # Collapsed to a single record → a single symbol.
    assert result.records_synced == 1
    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.symbol == "5450.TWO"
    assert stock.name == "南良"  # newest wins, stale 寶聯通 loses
    assert stock.market == Market.TW_TPEX
    # Fresh insert: no phantom rename.
    assert result.details["改名"] == 0
    assert result.details["新增"] == 1


async def test_second_identical_run_is_idempotent(db_session: AsyncSession) -> None:
    """Running the same duplicate-laden feed twice reports 改名=0 and is stable."""
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("5450", "寶聯通", "Other", "tpex", date="2020-06-03"),
        _record("5450", "南良", "Textiles", "tpex", date="2026-06-21"),
        _record("2330", "TSMC", "Semiconductor", "twse"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        first = await task.run(db_session, rl)
        # Second run against the now-populated DB.
        second = await task.run(db_session, rl)

    assert first.details["改名"] == 0
    # Idempotent: nothing renamed, everything unchanged on the second pass.
    assert second.details["改名"] == 0
    assert second.details["新增"] == 0
    assert second.details["未變動"] == 2

    # Row is NOT corrupted: 5450 is still 南良, not 寶聯通.
    rows = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    by_symbol = {s.symbol: s for s in rows}
    assert by_symbol["5450.TWO"].name == "南良"
    assert by_symbol["2330.TW"].name == "TSMC"


async def test_uplisted_stock_id_tpex_then_twse_newest_wins(db_session: AsyncSession) -> None:
    """6438 has tpex(old) + twse(new): dedup by stock_id resolves to twse listing."""
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("6438", "迅得", "Machinery", "tpex", date="2018-01-01"),
        _record("6438", "迅得", "Machinery", "twse", date="2026-06-21"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.records_synced == 1
    stock = (await db_session.execute(select(Stock))).scalar_one()
    # Newest listing is twse → ".TW" symbol + TW_TWSE market.
    assert stock.symbol == "6438.TW"
    assert stock.market == Market.TW_TWSE


async def test_genuine_rename_is_detected(db_session: AsyncSession) -> None:
    """When the newest-date record's name differs from the DB row, it IS a rename."""
    db_session.add(Stock(symbol="5450.TWO", name="寶聯通", market=Market.TW_TPEX))
    await db_session.commit()

    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("5450", "寶聯通", "Other", "tpex", date="2020-06-03"),
        _record("5450", "南良", "Textiles", "tpex", date="2026-06-21"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    # Newest (南良) differs from DB (寶聯通) → genuine rename detected once.
    assert result.details["改名"] == 1
    assert result.extras["改名範例"] == ["5450 寶聯通→南良"]
    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.name == "南良"


async def test_emerging_skipped_does_not_count_as_synced(db_session: AsyncSession) -> None:
    """A feed of only emerging records writes nothing but completes cleanly."""
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    raw = [
        _record("6173", "信昌電", "Electronics", "emerging"),
        _record("7777", "Foo", "Bar", "emerging"),
    ]
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "completed"
    assert result.records_synced == 0
    assert result.details["略過興櫃"] == 2
    stocks = (await db_session.execute(select(Stock))).scalars().all()
    assert stocks == []
