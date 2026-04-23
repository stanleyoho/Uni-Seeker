from unittest.mock import AsyncMock, MagicMock

from app.modules.company.twse_company import TWSECompanyProvider, INDUSTRY_MAP

SAMPLE = [
    {
        "公司代號": "2330", "公司名稱": "台灣積體電路製造股份有限公司",
        "公司簡稱": "台積電", "產業別": "24", "住址": "新竹市...",
        "董事長": "魏哲家", "總經理": "魏哲家",
        "成立日期": "19870221", "上市日期": "19940905",
        "實收資本額": "259303804580", "已發行普通股數或TDR原股發行股數": "25930380458",
        "英文簡稱": "TSMC",
    },
]


async def test_fetch_all_companies() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSECompanyProvider(client=mock_client)
    companies = await provider.fetch_all_companies()

    assert len(companies) == 1
    c = companies[0]
    assert c.symbol == "2330.TW"
    assert c.short_name == "台積電"
    assert c.industry_code == "24"
    assert c.industry_name == "半導體業"
    assert c.chairman == "魏哲家"
    assert c.capital == 259303804580
    assert c.shares_outstanding == 25930380458


def test_industry_map() -> None:
    assert INDUSTRY_MAP["24"] == "半導體業"
    assert INDUSTRY_MAP["15"] == "航運業"
    assert INDUSTRY_MAP["17"] == "金融保險業"


async def test_empty_response() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSECompanyProvider(client=mock_client)
    assert await provider.fetch_all_companies() == []
