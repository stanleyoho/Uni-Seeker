from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()

TPEX_QUOTES = "/tpex_mainboard_quotes"


class TPEXProvider:
    """Fetches daily stock prices from TPEX (Taiwan OTC) OpenAPI."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://www.tpex.org.tw/openapi/v1",
    ) -> None:
        self._client = client
        self._base_url = base_url

    @property
    def market(self) -> str:
        return "TW_TPEX"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        url = f"{self._base_url}{TPEX_QUOTES}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw_data: list[dict[str, str]] = response.json()

        prices: list[StockPriceData] = []
        today = date.today()

        for record in raw_data:
            code = record.get("SecuritiesCompanyCode", "")
            if symbol and code != symbol:
                continue

            try:
                price = StockPriceData(
                    symbol=f"{code}.TWO",
                    market=self.market,
                    date=today,
                    open=Decimal(record["Open"]),
                    high=Decimal(record["High"]),
                    low=Decimal(record["Low"]),
                    close=Decimal(record["Close"]),
                    volume=int(record["TradingShares"]),
                    change=Decimal(record.get("Change", "0")),
                    name=record.get("CompanyName", ""),
                )
                prices.append(price)
            except (InvalidOperation, ValueError, KeyError):
                logger.warning("skipping_invalid_tpex_record", code=code)
                continue

        return prices
