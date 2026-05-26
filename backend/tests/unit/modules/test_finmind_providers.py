"""Unit tests for `app.modules.finmind.{margin,stock}_provider`.

Both providers wrap `FinMindClient.fetch` and normalize the response;
we mock the client to test the normalization + error-handling paths.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.modules.finmind.margin_provider import FinMindMarginProvider
from app.modules.finmind.stock_provider import FinMindStockProvider


# ── FinMindMarginProvider ────────────────────────────────────────────────


async def test_margin_provider_forwards_to_client() -> None:
    """The provider is a thin wrapper — verify it calls FinMindClient.fetch
    with the right dataset + kwargs and returns the raw payload."""
    expected = [{"date": "2026-05-01", "MarginPurchaseBuy": 1000}]
    client = AsyncMock()
    client.fetch.return_value = expected

    provider = FinMindMarginProvider(client=client)
    result = await provider.fetch_margin("2330", "2026-05-01", "2026-05-31")

    assert result == expected
    client.fetch.assert_awaited_once_with(
        dataset="TaiwanStockMarginPurchaseShortSale",
        data_id="2330",
        start_date="2026-05-01",
        end_date="2026-05-31",
    )


async def test_margin_provider_empty_response() -> None:
    client = AsyncMock()
    client.fetch.return_value = []

    provider = FinMindMarginProvider(client=client)
    result = await provider.fetch_margin("2330", "2026-05-01", "2026-05-31")
    assert result == []


def test_margin_provider_default_client_constructed_when_omitted() -> None:
    """No client → falls back to a real FinMindClient (don't actually call)."""
    provider = FinMindMarginProvider()
    assert provider._client is not None


# ── FinMindStockProvider ─────────────────────────────────────────────────


async def test_stock_provider_normalizes_records() -> None:
    """Raw FinMind dicts → StockPriceData with TW market + Decimal-cast values."""
    raw = [
        {
            "stock_id": "2330",
            "date": "2026-05-01",
            "open": 580,
            "max": 590,
            "min": 575,
            "close": 588,
            "Trading_Volume": 30_000_000,
            "spread": 5,
        }
    ]
    client = AsyncMock()
    client.fetch.return_value = raw

    provider = FinMindStockProvider(client=client)
    prices = await provider.fetch_daily_prices("2330", "2026-05-01", "2026-05-01")

    assert len(prices) == 1
    p = prices[0]
    assert p.symbol == "2330.TW"
    assert p.market == "TW_TWSE"
    assert p.date == date(2026, 5, 1)
    assert p.open == Decimal("580")
    assert p.high == Decimal("590")
    assert p.low == Decimal("575")
    assert p.close == Decimal("588")
    assert p.volume == 30_000_000
    assert p.change == Decimal("5")


async def test_stock_provider_skips_invalid_record() -> None:
    """Bad record (missing key) is logged + skipped, not raised."""
    raw = [
        {
            "stock_id": "2330",
            "date": "2026-05-01",
            "open": 580,
            "max": 590,
            "min": 575,
            "close": 588,
            "Trading_Volume": 30_000_000,
            "spread": 5,
        },
        # Missing close / Trading_Volume — skip
        {"stock_id": "2330", "date": "2026-05-02"},
    ]
    client = AsyncMock()
    client.fetch.return_value = raw

    provider = FinMindStockProvider(client=client)
    prices = await provider.fetch_daily_prices("2330", "2026-05-01", "2026-05-02")
    assert len(prices) == 1


async def test_stock_provider_skips_bad_decimal() -> None:
    """Non-decimal price string is logged + skipped."""
    raw = [
        {
            "stock_id": "2330",
            "date": "2026-05-01",
            "open": "not-a-number",
            "max": 590,
            "min": 575,
            "close": 588,
            "Trading_Volume": 30_000_000,
            "spread": 5,
        }
    ]
    client = AsyncMock()
    client.fetch.return_value = raw

    provider = FinMindStockProvider(client=client)
    prices = await provider.fetch_daily_prices("2330", "2026-05-01", "2026-05-01")
    assert prices == []


def test_stock_provider_market_constant() -> None:
    """market property is the TW_TWSE constant (used by upserter)."""
    assert FinMindStockProvider().market == "TW_TWSE"


def test_stock_provider_default_client_constructed_when_omitted() -> None:
    provider = FinMindStockProvider()
    assert provider._client is not None
