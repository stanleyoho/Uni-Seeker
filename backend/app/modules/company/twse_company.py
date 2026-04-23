from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

TWSE_COMPANY_INFO = "/opendata/t187ap03_L"

INDUSTRY_MAP = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業",
    "04": "紡織纖維", "05": "電機機械", "06": "電器電纜",
    "07": "化學生技醫療", "21": "化學工業", "22": "生技醫療業",
    "08": "玻璃陶瓷", "09": "造紙工業", "10": "鋼鐵工業",
    "11": "橡膠工業", "12": "汽車工業", "13": "電子工業",
    "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業",
    "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
    "30": "資訊服務業", "31": "其他電子業",
    "14": "建材營造業", "15": "航運業", "16": "觀光餐旅",
    "17": "金融保險業", "18": "貿易百貨業", "23": "油電燃氣業",
    "19": "綜合", "20": "其他業",
    "32": "文化創意業", "33": "農業科技業", "34": "電子商務業",
    "35": "運動休閒", "36": "居家生活", "80": "管理股票",
}


@dataclass(frozen=True)
class CompanyInfo:
    symbol: str
    full_name: str
    short_name: str
    industry_code: str
    industry_name: str
    chairman: str
    ceo: str
    capital: int  # 實收資本額
    shares_outstanding: int  # 已發行股數
    established_date: str
    listed_date: str
    english_name: str
    address: str


class TWSECompanyProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://openapi.twse.com.tw/v1") -> None:
        self._client = client
        self._base_url = base_url

    async def fetch_all_companies(self) -> list[CompanyInfo]:
        url = f"{self._base_url}{TWSE_COMPANY_INFO}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw: list[dict[str, str]] = response.json()

        results: list[CompanyInfo] = []
        for item in raw:
            code = item.get("公司代號", "").strip()
            if not code:
                continue

            industry_code = item.get("產業別", "").strip()
            industry_name = INDUSTRY_MAP.get(industry_code, industry_code)

            # Parse capital
            try:
                capital = int(item.get("實收資本額", "0"))
            except ValueError:
                capital = 0
            try:
                shares = int(item.get("已發行普通股數或TDR原股發行股數", "0"))
            except ValueError:
                shares = 0

            results.append(CompanyInfo(
                symbol=f"{code}.TW",
                full_name=item.get("公司名稱", ""),
                short_name=item.get("公司簡稱", ""),
                industry_code=industry_code,
                industry_name=industry_name,
                chairman=item.get("董事長", ""),
                ceo=item.get("總經理", ""),
                capital=capital,
                shares_outstanding=shares,
                established_date=item.get("成立日期", ""),
                listed_date=item.get("上市日期", ""),
                english_name=item.get("英文簡稱", ""),
                address=item.get("住址", ""),
            ))

        logger.info("twse_company_fetched", count=len(results))
        return results
