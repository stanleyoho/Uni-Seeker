from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

from app.modules.price_updater.base import StockPriceData
from app.modules.price_updater.updater import PriceUpdater


def _make_price(symbol: str = "2330.TW", close: str = "890.00") -> StockPriceData:
    return StockPriceData(
        symbol=symbol,
        market="TW_TWSE",
        date=date(2026, 4, 22),
        open=Decimal("885.00"),
        high=Decimal("892.00"),
        low=Decimal("880.00"),
        close=Decimal(close),
        volume=25_000_000,
    )


async def test_updater_calls_providers() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [_make_price()]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    provider.fetch_daily_prices.assert_awaited_once()
    assert result.total_fetched == 1


async def test_updater_deduplicates_by_symbol_date() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [_make_price(), _make_price()]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    assert result.total_fetched == 2
    assert result.duplicates_skipped == 1


async def test_updater_validates_prices() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [
        _make_price(close="0.00"),
        _make_price(symbol="2317.TW", close="178.00"),
    ]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    assert result.total_fetched == 2
    assert result.invalid_skipped == 1


async def test_updater_retries_on_failure() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.side_effect = [
        Exception("network error"),
        [_make_price()],
    ]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session, max_retries=2)
    result = await updater.update_all()

    assert provider.fetch_daily_prices.await_count == 2
    assert result.total_fetched == 1


async def test_updater_gives_up_after_max_retries() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.side_effect = Exception("permanent failure")
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session, max_retries=3)
    result = await updater.update_all()

    assert provider.fetch_daily_prices.await_count == 3
    assert result.total_fetched == 0
    assert len(result.errors) == 1
