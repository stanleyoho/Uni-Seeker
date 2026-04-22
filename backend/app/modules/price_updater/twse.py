from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()

TWSE_STOCK_DAY_ALL = "/exchangeReport/STOCK_DAY_ALL"


class TWSEProvider:
    """Fetches daily stock prices from TWSE OpenAPI."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://openapi.twse.com.tw/v1",
    ) -> None:
        self._client = client
        self._base_url = base_url

    @property
    def market(self) -> str:
        return "TW_TWSE"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        url = f"{self._base_url}{TWSE_STOCK_DAY_ALL}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw_data: list[dict[str, str]] = response.json()

        prices: list[StockPriceData] = []
        today = date.today()

        for record in raw_data:
            code = record.get("Code", "")
            if symbol and code != symbol:
                continue

            try:
                price = StockPriceData(
                    symbol=f"{code}.TW",
                    market=self.market,
                    date=today,
                    open=Decimal(record["OpeningPrice"]),
                    high=Decimal(record["HighestPrice"]),
                    low=Decimal(record["LowestPrice"]),
                    close=Decimal(record["ClosingPrice"]),
                    volume=int(record["TradeVolume"]),
                    change=Decimal(record.get("Change", "0")),
                    name=record.get("Name", ""),
                )
                prices.append(price)
            except (InvalidOperation, ValueError, KeyError):
                logger.warning("skipping_invalid_record", code=code)
                continue

        return prices
