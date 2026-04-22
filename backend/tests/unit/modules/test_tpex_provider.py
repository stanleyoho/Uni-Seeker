from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.modules.price_updater.base import DataProvider
from app.modules.price_updater.tpex import TPEXProvider

TPEX_SAMPLE_RESPONSE = [
    {
        "SecuritiesCompanyCode": "6510",
        "CompanyName": "精測",
        "Close": "530.00",
        "Open": "525.00",
        "High": "535.00",
        "Low": "523.00",
        "TradingShares": "1200000",
        "Change": "8.00",
    },
]


def test_tpex_provider_is_data_provider() -> None:
    provider = TPEXProvider(client=AsyncMock())
    assert isinstance(provider, DataProvider)


async def test_tpex_fetch_daily_prices() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = TPEX_SAMPLE_RESPONSE
    mock_response.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_response

    provider = TPEXProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert len(prices) == 1
    assert prices[0].symbol == "6510.TWO"
    assert prices[0].market == "TW_TPEX"
    assert prices[0].close == Decimal("530.00")
    assert prices[0].volume == 1_200_000


async def test_tpex_handles_empty_response() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_response

    provider = TPEXProvider(client=mock_client)
    assert await provider.fetch_daily_prices() == []
