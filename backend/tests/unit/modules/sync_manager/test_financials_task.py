"""Unit tests for FinancialsSyncTask and helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.financial_statement import FinancialStatement
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindRateLimitError
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.financials import (
    FinancialsSyncTask,
    _date_to_period,
    _pivot_eav,
)


def _eav(date_str: str, type_: str, value: float) -> dict[str, Any]:
    return {"date": date_str, "type": type_, "value": value}


# ---------- helper unit tests ----------------------------------------------


def test_pivot_eav_groups_by_date() -> None:
    out = _pivot_eav(
        [
            _eav("2024-03-31", "Revenue", 100),
            _eav("2024-03-31", "NetIncome", 30),
            _eav("2024-06-30", "Revenue", 200),
        ]
    )
    assert out == {
        "2024-03-31": {"Revenue": 100.0, "NetIncome": 30.0},
        "2024-06-30": {"Revenue": 200.0},
    }


def test_pivot_eav_skips_missing_or_none() -> None:
    out = _pivot_eav(
        [
            {"date": "", "type": "X", "value": 1},
            {"date": "2024-03-31", "type": "", "value": 1},
            {"date": "2024-03-31", "type": "X", "value": None},
            _eav("2024-03-31", "Y", 5),
        ]
    )
    assert out == {"2024-03-31": {"Y": 5.0}}


@pytest.mark.parametrize(
    "date_str,expected",
    [
        ("2024-03-31", ("2024-Q1", 2024, 1)),
        ("2024-06-30", ("2024-Q2", 2024, 2)),
        ("2024-09-30", ("2024-Q3", 2024, 3)),
        ("2024-12-31", ("2024-Q4", 2024, 4)),
    ],
)
def test_date_to_period_quarter_ends(date_str: str, expected: tuple[str, int, int]) -> None:
    assert _date_to_period(date_str) == expected


def test_date_to_period_returns_none_for_non_quarter_month() -> None:
    assert _date_to_period("2024-07-15") is None


def test_date_to_period_returns_none_for_bad_string() -> None:
    assert _date_to_period("not-a-date") is None
    assert _date_to_period("") is None


# ---------- task tests ------------------------------------------------------


async def _add_stock(db: AsyncSession, symbol: str = "2330.TW") -> Stock:
    stock = Stock(symbol=symbol, name="TestCo", market=Market.TW_TWSE)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    return stock


async def test_run_no_active_stocks(db_session: AsyncSession) -> None:
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    result = await task.run(db_session, rl)

    assert result.dataset == "financials"
    assert result.stopped_reason == "completed"
    assert result.stocks_processed == 0


async def test_run_skip_up_to_date(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    # Match production sync task: today is computed in Asia/Taipei.
    # Naive datetime.now() returns local-tz date, which is UTC on CI runners
    # and Taipei on Stanley's machine — using ZoneInfo aligns both.
    today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
    db_session.add(
        SyncState(
            dataset="financials",
            stock_id=stock.id,
            last_synced_date=today,
            last_run_at=datetime.now(UTC),
            status="completed",
            records_synced=1,
            error_message=None,
        )
    )
    await db_session.commit()

    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)
    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=[])
        result = await task.run(db_session, rl)

    assert result.stocks_processed == 0
    client_cls.return_value.fetch.assert_not_awaited()


async def test_run_inserts_statements_for_all_three_types(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    # 3 datasets are fetched in order: income, balance, cashflow.
    # Provide a single EAV record for each so we get exactly 3 inserts.
    income = [_eav("2024-03-31", "Revenue", 100)]
    balance = [_eav("2024-03-31", "TotalAssets", 1000)]
    cashflow = [_eav("2024-03-31", "OperatingCashFlow", 50)]

    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=[income, balance, cashflow])
        result = await task.run(db_session, rl)

    assert result.records_synced == 3
    assert result.stopped_reason == "completed"
    rows = (await db_session.execute(select(FinancialStatement))).scalars().all()
    types = {r.statement_type for r in rows}
    assert types == {"income", "balance", "cashflow"}
    for r in rows:
        assert r.period == "2024-Q1"
        assert r.fiscal_year == 2024
        assert r.fiscal_quarter == 1


async def test_run_skips_invalid_period_dates(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    # Mix of valid Q-end and invalid month dates
    income = [
        _eav("2024-07-15", "X", 1),  # invalid (not Q-end)
        _eav("2024-03-31", "Revenue", 100),  # valid
    ]
    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=[income, [], []])
        result = await task.run(db_session, rl)

    assert result.records_synced == 1


async def test_run_handles_fetch_error_per_dataset(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        # Income raises, balance succeeds, cashflow succeeds
        client_cls.return_value.fetch = AsyncMock(
            side_effect=[
                RuntimeError("boom"),
                [_eav("2024-03-31", "Assets", 10)],
                [_eav("2024-03-31", "OCF", 5)],
            ]
        )
        result = await task.run(db_session, rl)

    assert result.errors == 1
    assert result.records_synced == 2


async def test_run_breaks_on_rate_limit_error(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=FinMindRateLimitError())
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_breaks_when_rate_limiter_exhausted(db_session: AsyncSession) -> None:
    await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    with patch.object(rl, "wait_and_acquire", AsyncMock(return_value=False)):
        result = await task.run(db_session, rl)

    assert result.stopped_reason == "rate_limit"


async def test_run_max_date_tracked_for_sync_state(db_session: AsyncSession) -> None:
    stock = await _add_stock(db_session)
    task = FinancialsSyncTask()
    rl = RateLimiter(max_requests=10, window_seconds=60)

    income = [_eav("2024-03-31", "Revenue", 100), _eav("2024-06-30", "Revenue", 200)]
    with patch("app.modules.sync_manager.tasks.financials.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(side_effect=[income, [], []])
        await task.run(db_session, rl)

    state = (await db_session.execute(select(SyncState))).scalar_one()
    assert state.stock_id == stock.id
    assert state.last_synced_date == date(2024, 6, 30)
