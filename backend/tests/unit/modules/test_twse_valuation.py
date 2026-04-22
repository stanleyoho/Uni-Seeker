from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.modules.valuation.base import ValuationProvider
from app.modules.valuation.twse_valuation import TWSEValuationProvider

BWIBBU_SAMPLE = [
    {
        "Code": "2330", "Name": "\u53f0\u7a4d\u96fb",
        "PEratio": "22.50", "DividendYield": "1.80", "PBratio": "5.60",
    },
    {
        "Code": "2317", "Name": "\u9d3b\u6d77",
        "PEratio": "12.47", "DividendYield": "6.52", "PBratio": "0.69",
    },
    {
        "Code": "1101", "Name": "\u53f0\u6ce5",
        "PEratio": "", "DividendYield": "3.23", "PBratio": "0.82",
    },
]


def test_provider_is_valuation_provider() -> None:
    provider = TWSEValuationProvider(client=AsyncMock())
    assert isinstance(provider, ValuationProvider)


async def test_fetch_all_valuations() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = BWIBBU_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp
    provider = TWSEValuationProvider(client=mock_client)
    data = await provider.fetch_valuations()
    assert len(data) == 3
    assert data[0].symbol == "2330.TW"
    assert data[0].pe_ratio == Decimal("22.50")
    assert data[0].pb_ratio == Decimal("5.60")


async def test_empty_pe_is_none() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = BWIBBU_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp
    provider = TWSEValuationProvider(client=mock_client)
    data = await provider.fetch_valuations()
    assert data[2].pe_ratio is None
    assert data[2].dividend_yield == Decimal("3.23")


async def test_fetch_empty_response() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp
    provider = TWSEValuationProvider(client=mock_client)
    assert await provider.fetch_valuations() == []
