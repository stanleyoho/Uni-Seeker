"""Integration tests for TwInstitutionalSyncTask."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.enums import Market
from app.models.stock import Stock
from app.models.tw_institutional import TwInstitutionalNet
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.tw_institutional import (
    TwInstitutionalSyncTask,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def rate_limiter() -> RateLimiter:
    # Generous budget so the test isn't accidentally rate-gated.
    return RateLimiter(max_requests=1000)


async def test_sync_writes_aggregated_rows(
    db_session: AsyncSession,
    rate_limiter: RateLimiter,
) -> None:
    stock = Stock(symbol="2330", name="台積電", market=Market.TW_TWSE)
    db_session.add(stock)
    await db_session.commit()

    raw = [
        {
            "date": "2026-05-29",
            "name": "Foreign_Investor",
            "buy": 10_000_000,
            "sell": 5_000_000,
        },
        {
            "date": "2026-05-29",
            "name": "Investment_Trust",
            "buy": 2_000_000,
            "sell": 500_000,
        },
        {
            "date": "2026-05-29",
            "name": "Dealer_self",
            "buy": 100_000,
            "sell": 200_000,
        },
        {
            "date": "2026-05-29",
            "name": "Dealer_Hedging",
            "buy": 300_000,
            "sell": 100_000,
        },
    ]

    with patch("app.modules.sync_manager.tasks.tw_institutional.FinMindClient") as client_cls:
        client_cls.return_value.fetch = AsyncMock(return_value=raw)
        task = TwInstitutionalSyncTask()
        result = await task.run(db_session, rate_limiter, batch_size=50)

    assert result.errors == 0
    assert result.records_synced == 1
    assert result.stopped_reason == "completed"

    rows = (
        (
            await db_session.execute(
                select(TwInstitutionalNet).where(TwInstitutionalNet.stock_id == stock.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.date == date(2026, 5, 29)
    assert row.foreign_net == 5_000_000
    assert row.trust_net == 1_500_000
    # dealer_self (-100k) + dealer_hedging (+200k) = +100k
    assert row.dealer_net == 100_000
    assert row.total_net == 6_600_000


async def test_sync_handles_no_active_stocks(
    db_session: AsyncSession,
    rate_limiter: RateLimiter,
) -> None:
    task = TwInstitutionalSyncTask()
    result = await task.run(db_session, rate_limiter, batch_size=50)
    assert result.stopped_reason == "completed"
    assert result.records_synced == 0


async def test_sync_skips_stock_on_fetch_error(
    db_session: AsyncSession,
    rate_limiter: RateLimiter,
) -> None:
    """Bad ticker must not abort the whole batch."""
    a = Stock(symbol="2330", name="台積電", market=Market.TW_TWSE)
    b = Stock(symbol="2454", name="聯發科", market=Market.TW_TWSE)
    db_session.add_all([a, b])
    await db_session.commit()

    call_count = {"n": 0}

    async def fake_fetch(*args: object, **kwargs: object) -> list[dict]:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated 4xx")
        return [
            {
                "date": "2026-05-29",
                "name": "Foreign_Investor",
                "buy": 100,
                "sell": 50,
            }
        ]

    with patch("app.modules.sync_manager.tasks.tw_institutional.FinMindClient") as client_cls:
        client_cls.return_value.fetch = fake_fetch
        task = TwInstitutionalSyncTask()
        result = await task.run(db_session, rate_limiter, batch_size=50)

    assert result.errors == 1
    # One stock still made it through.
    assert result.records_synced == 1
    assert result.stopped_reason == "completed"
