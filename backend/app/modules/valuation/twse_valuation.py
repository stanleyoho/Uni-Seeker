from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.valuation.base import ValuationData

logger = structlog.get_logger()
BWIBBU_ALL = "/exchangeReport/BWIBBU_ALL"


class TWSEValuationProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://openapi.twse.com.tw/v1",
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def fetch_valuations(self) -> list[ValuationData]:
        url = f"{self._base_url}{BWIBBU_ALL}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw: list[dict[str, str]] = response.json()
        results: list[ValuationData] = []
        today = date.today()

        for record in raw:
            code = record.get("Code", "")
            pe_str = record.get("PEratio", "").strip()
            pb_str = record.get("PBratio", "").strip()
            dy_str = record.get("DividendYield", "").strip()

            try:
                pe = Decimal(pe_str) if pe_str else None
            except InvalidOperation:
                pe = None
            try:
                pb = Decimal(pb_str) if pb_str else None
            except InvalidOperation:
                pb = None
            try:
                dy = Decimal(dy_str) if dy_str else None
            except InvalidOperation:
                dy = None

            results.append(
                ValuationData(
                    symbol=f"{code}.TW",
                    name=record.get("Name", ""),
                    date=today,
                    pe_ratio=pe,
                    pb_ratio=pb,
                    dividend_yield=dy,
                )
            )
        return results
