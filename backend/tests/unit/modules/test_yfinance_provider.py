from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd

from app.modules.price_updater.base import DataProvider
from app.modules.price_updater.yfinance_provider import YFinanceProvider


def _make_mock_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [150.0, 152.0],
            "High": [155.0, 156.0],
            "Low": [149.0, 151.0],
            "Close": [153.0, 154.5],
            "Volume": [80_000_000, 75_000_000],
        },
        index=pd.DatetimeIndex([date(2026, 4, 21), date(2026, 4, 22)], name="Date"),
    )


def test_yfinance_provider_is_data_provider() -> None:
    provider = YFinanceProvider()
    assert isinstance(provider, DataProvider)


async def test_yfinance_fetch_single_stock() -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_mock_history()
    mock_ticker.info = {"exchange": "NMS"}

    with patch("app.modules.price_updater.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceProvider()
        prices = await provider.fetch_daily_prices(symbol="AAPL")

    assert len(prices) == 2
    assert prices[0].symbol == "AAPL"
    assert prices[0].market == "US_NASDAQ"
    assert prices[0].close == Decimal("153.0")
    assert prices[0].volume == 80_000_000


async def test_yfinance_empty_history() -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("app.modules.price_updater.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceProvider()
        prices = await provider.fetch_daily_prices(symbol="INVALID")

    assert prices == []
