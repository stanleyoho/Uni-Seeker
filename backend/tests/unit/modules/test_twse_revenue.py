from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.revenue.twse_revenue import TWSERevenueProvider

SAMPLE = [
    {
        "出表日期": "1150417",
        "資料年月": "11503",
        "公司代號": "2330",
        "公司名稱": "台積電",
        "產業別": "半導體業",
        "營業收入-當月營收": "278061367",
        "營業收入-上月營收": "260013056",
        "營業收入-去年當月營收": "208993413",
        "營業收入-上月比較增減(%)": "6.94",
        "營業收入-去年同月增減(%)": "33.04",
        "累計營業收入-當月累計營收": "793483740",
        "累計營業收入-去年累計營收": "600009428",
        "累計營業收入-前期比較增減(%)": "32.25",
        "備註": "-",
    },
]


@pytest.mark.asyncio
async def test_fetch_all_revenue() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSERevenueProvider(client=mock_client)
    records = await provider.fetch_all_revenue()

    assert len(records) == 1
    rec = records[0]
    assert rec.symbol == "2330.TW"
    assert rec.period == "2026-03"
    assert rec.period_type == "monthly"
    assert rec.revenue == 278061367
    assert rec.yoy_growth == 33.04
    assert rec.mom_growth == 6.94
    assert rec.industry == "半導體業"
    assert rec.currency == "TWD"


@pytest.mark.asyncio
async def test_empty_response() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSERevenueProvider(client=mock_client)
    assert await provider.fetch_all_revenue() == []


@pytest.mark.asyncio
async def test_skips_invalid_date() -> None:
    bad_item = {**SAMPLE[0], "資料年月": "bad"}
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [bad_item]
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSERevenueProvider(client=mock_client)
    assert await provider.fetch_all_revenue() == []


@pytest.mark.asyncio
async def test_skips_empty_code() -> None:
    bad_item = {**SAMPLE[0], "公司代號": ""}
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [bad_item]
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSERevenueProvider(client=mock_client)
    assert await provider.fetch_all_revenue() == []
