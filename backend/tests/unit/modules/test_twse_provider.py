from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.modules.price_updater.base import DataProvider
from app.modules.price_updater.twse import TWSEProvider

TWSE_SAMPLE_RESPONSE = [
    {
        "Code": "2330",
        "Name": "台積電",
        "TradeVolume": "25000000",
        "TradeValue": "22250000000",
        "OpeningPrice": "885.00",
        "HighestPrice": "892.00",
        "LowestPrice": "880.00",
        "ClosingPrice": "890.00",
        "Change": "5.00",
        "Transaction": "45000",
    },
    {
        "Code": "2317",
        "Name": "鴻海",
        "TradeVolume": "18000000",
        "TradeValue": "3204000000",
        "OpeningPrice": "178.00",
        "HighestPrice": "180.00",
        "LowestPrice": "177.00",
        "ClosingPrice": "178.50",
        "Change": "-0.50",
        "Transaction": "30000",
    },
]


def test_twse_provider_is_data_provider() -> None:
    client = AsyncMock()
    provider = TWSEProvider(client=client)
    assert isinstance(provider, DataProvider)


async def test_twse_fetch_daily_prices() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = TWSE_SAMPLE_RESPONSE
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert len(prices) == 2
    tsmc = prices[0]
    assert tsmc.symbol == "2330.TW"
    assert tsmc.close == Decimal("890.00")
    assert tsmc.volume == 25_000_000
    assert tsmc.market == "TW_TWSE"

    hon_hai = prices[1]
    assert hon_hai.symbol == "2317.TW"
    assert hon_hai.close == Decimal("178.50")


async def test_twse_fetch_single_stock() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = [TWSE_SAMPLE_RESPONSE[0]]
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices(symbol="2330")
    assert len(prices) == 1
    assert prices[0].symbol == "2330.TW"


async def test_twse_handles_empty_response() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()
    assert prices == []


async def test_twse_skips_invalid_prices() -> None:
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "Code": "9999",
            "Name": "暫停交易",
            "TradeVolume": "0",
            "TradeValue": "0",
            "OpeningPrice": "--",
            "HighestPrice": "--",
            "LowestPrice": "--",
            "ClosingPrice": "--",
            "Change": "0",
            "Transaction": "0",
        },
        TWSE_SAMPLE_RESPONSE[0],
    ]
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()
    assert len(prices) == 1
    assert prices[0].symbol == "2330.TW"
