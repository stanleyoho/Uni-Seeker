from datetime import date

import httpx
import structlog

from app.modules.margin.base import MarginData

logger = structlog.get_logger()

MI_MARGN = "/exchangeReport/MI_MARGN"


def _parse_int(s: str) -> int:
    s = s.strip().replace(",", "")
    return int(s) if s else 0


class TWSEMarginProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://openapi.twse.com.tw/v1") -> None:
        self._client = client
        self._base_url = base_url

    async def fetch_margin_data(self) -> list[MarginData]:
        url = f"{self._base_url}{MI_MARGN}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw: list[dict[str, str]] = response.json()

        results: list[MarginData] = []
        today = date.today()

        for item in raw:
            code = item.get("股票代號", "").strip()
            if not code:
                continue

            results.append(MarginData(
                symbol=f"{code}.TW",
                name=item.get("股票名稱", ""),
                date=today,
                margin_buy=_parse_int(item.get("融資買進", "")),
                margin_sell=_parse_int(item.get("融資賣出", "")),
                margin_cash_repay=_parse_int(item.get("融資現金償還", "")),
                margin_balance_prev=_parse_int(item.get("融資前日餘額", "")),
                margin_balance=_parse_int(item.get("融資今日餘額", "")),
                margin_limit=_parse_int(item.get("融資限額", "")),
                short_buy=_parse_int(item.get("融券買進", "")),
                short_sell=_parse_int(item.get("融券賣出", "")),
                short_cash_repay=_parse_int(item.get("融券現券償還", "")),
                short_balance_prev=_parse_int(item.get("融券前日餘額", "")),
                short_balance=_parse_int(item.get("融券今日餘額", "")),
                short_limit=_parse_int(item.get("融券限額", "")),
                offset=_parse_int(item.get("資券互抵", "")),
            ))

        logger.info("twse_margin_fetched", count=len(results))
        return results
