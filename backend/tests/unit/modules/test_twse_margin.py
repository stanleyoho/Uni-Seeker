from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.modules.margin.twse_margin import TWSEMarginProvider, _parse_int


SAMPLE = [
    {
        "股票代號": "2330", "股票名稱": "台積電",
        "融資買進": "2965", "融資賣出": "836", "融資現金償還": "",
        "融資前日餘額": "9551", "融資今日餘額": "11680", "融資限額": "338535",
        "融券買進": "", "融券賣出": "1", "融券現券償還": "",
        "融券前日餘額": "3", "融券今日餘額": "4", "融券限額": "338535",
        "資券互抵": "17", "註記": " ",
    },
]


def test_parse_int() -> None:
    assert _parse_int("2965") == 2965
    assert _parse_int("") == 0
    assert _parse_int(" ") == 0
    assert _parse_int("1,234") == 1234


async def test_fetch_margin_data() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSEMarginProvider(client=mock_client)
    data = await provider.fetch_margin_data()

    assert len(data) == 1
    d = data[0]
    assert d.symbol == "2330.TW"
    assert d.margin_buy == 2965
    assert d.margin_balance == 11680
    assert d.short_balance == 4
    assert d.offset == 17


async def test_empty_response() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSEMarginProvider(client=mock_client)
    assert await provider.fetch_margin_data() == []


def test_margin_data_fields() -> None:
    from app.modules.margin.base import MarginData
    d = MarginData(
        symbol="2330.TW", name="台積電", date=date.today(),
        margin_buy=100, margin_sell=50, margin_cash_repay=0,
        margin_balance_prev=500, margin_balance=550, margin_limit=10000,
        short_buy=0, short_sell=10, short_cash_repay=0,
        short_balance_prev=20, short_balance=30, short_limit=10000,
        offset=5,
    )
    assert d.margin_balance == 550
    assert d.short_balance == 30
