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
    # Both rows are brand new → both written.
    assert result.records_synced == 2
    assert result.stocks_processed == 2

    stocks = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    # OTC (3008) must use the .TWO suffix; TWSE (2330) uses .TW. The OTC
    # row used to be mis-suffixed as ".TW", colliding with the TWSE row of
    # the same numeric id — see UNI sync bug fix.
    assert [s.symbol for s in stocks] == ["2330.TW", "3008.TWO"]
    # OTC should map to TW_TPEX, others TW_TWSE
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


async def _run_with(db: AsyncSession, raw: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    """Run StockInfoSyncTask once with a mocked provider returning *raw*."""
    task = StockInfoSyncTask()
    rl = RateLimiter(max_requests=100, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.stock_info.FinMindMarketProvider") as provider_cls:
        provider_cls.return_value.fetch_stock_info = AsyncMock(return_value=raw)
        return await task.run(db, rl)


# ── Defect #1: OTC suffix ───────────────────────────────────────────────────


async def test_otc_record_uses_two_suffix(db_session: AsyncSession) -> None:
    """An OTC (type='OTC') record must be upserted as `<id>.TWO`, not `.TW`."""
    await _run_with(db_session, [_record("5450", "寶聯通", "電子零組件", "OTC")])

    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.symbol == "5450.TWO"
    assert stock.market == Market.TW_TPEX


async def test_twse_record_uses_tw_suffix(db_session: AsyncSession) -> None:
    """A non-OTC record keeps the `.TW` suffix and TW_TWSE market."""
    await _run_with(db_session, [_record("2330", "TSMC", "Semiconductor", "twse")])

    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.symbol == "2330.TW"
    assert stock.market == Market.TW_TWSE


async def test_otc_and_twse_same_numeric_id_do_not_collide(db_session: AsyncSession) -> None:
    """Regression: an OTC id and a TWSE id sharing the same digits (5450)
    must produce two distinct rows (5450.TWO vs 5450.TW), not collide.

    Before the fix both were built as `5450.TW`, so the second record
    overwrote the first via on_conflict_do_update and only one row survived.
    """
    raw = [
        _record("5450", "南良", "紡織纖維", "twse"),  # TWSE 5450
        _record("5450", "寶聯通", "電子零組件", "OTC"),  # OTC 5450
    ]
    result = await _run_with(db_session, raw)

    stocks = (await db_session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
    by_symbol = {s.symbol: s for s in stocks}
    assert set(by_symbol) == {"5450.TW", "5450.TWO"}
    assert by_symbol["5450.TW"].name == "南良"
    assert by_symbol["5450.TW"].market == Market.TW_TWSE
    assert by_symbol["5450.TWO"].name == "寶聯通"
    assert by_symbol["5450.TWO"].market == Market.TW_TPEX
    # Both rows are new → both written.
    assert result.records_synced == 2
    assert result.stocks_processed == 2


# ── Defect #2: idempotency / no phantom rename, no needless rewrite ──────────


async def test_second_identical_run_is_idempotent_no_phantom_rename(
    db_session: AsyncSession,
) -> None:
    """A second identical run reports 改名=0 and 未變動 increments, and does
    NOT re-write the unchanged row (updated_at must be unchanged)."""
    raw = [_record("5450", "寶聯通", "電子零組件", "OTC")]

    first = await _run_with(db_session, raw)
    assert first.details["新增"] == 1
    assert first.records_synced == 1  # one row written (the new insert)

    # Capture updated_at after the first run.
    stock_after_first = (await db_session.execute(select(Stock))).scalar_one()
    updated_at_first = stock_after_first.updated_at

    second = await _run_with(db_session, raw)

    # No phantom rename / industry / market change on the identical feed.
    assert second.details["改名"] == 0
    assert second.details["換產業"] == 0
    assert second.details["上下市"] == 0
    assert second.details["未變動"] == 1
    assert second.details["新增"] == 0
    # The unchanged row was NOT re-written.
    assert second.records_synced == 0  # rows actually written
    assert second.stocks_processed == 1  # total records processed

    stock_after_second = (await db_session.execute(select(Stock))).scalar_one()
    # Row identity + content unchanged; updated_at not bumped because the
    # no-op upsert was skipped.
    assert stock_after_second.symbol == "5450.TWO"
    assert stock_after_second.name == "寶聯通"
    assert stock_after_second.updated_at == updated_at_first


async def test_otc_genuine_rename_is_detected(db_session: AsyncSession) -> None:
    """An OTC stock whose name genuinely changed is detected as a rename and
    its row is updated (matched on the correct .TWO symbol)."""
    # Seed an existing OTC row under its correct .TWO symbol.
    db_session.add(Stock(symbol="5450.TWO", name="OldOTCName", market=Market.TW_TPEX))
    await db_session.commit()

    result = await _run_with(
        db_session, [_record("5450", "NewOTCName", "電子零組件", "OTC")]
    )

    assert result.details["改名"] == 1
    assert result.details["新增"] == 0
    assert result.details["未變動"] == 0
    assert result.records_synced == 1  # the changed row was written
    assert result.extras["改名範例"] == ["5450 OldOTCName→NewOTCName"]

    stock = (await db_session.execute(select(Stock))).scalar_one()
    assert stock.symbol == "5450.TWO"
    assert stock.name == "NewOTCName"


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
