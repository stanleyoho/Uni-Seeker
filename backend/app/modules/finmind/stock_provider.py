"""FinMind provider for Taiwan stock daily prices."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import structlog

from app.config import settings
from app.modules.finmind.client import FinMindClient
from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()


class FinMindStockProvider:
    """Fetches daily stock prices from FinMind ``TaiwanStockPrice`` dataset."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._client = client or FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

    @property
    def market(self) -> str:
        return "TW_TWSE"

    async def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> list[StockPriceData]:
        """Fetch daily OHLCV data for a single stock.

        Parameters
        ----------
        stock_id : str
            Taiwan stock symbol (e.g. ``"2330"``).
        start_date : str
            ISO start date.
        end_date : str
            ISO end date.

        Returns
        -------
        list[StockPriceData]
            Normalised price records.
        """
        raw = await self._client.fetch(
            dataset="TaiwanStockPrice",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )

        prices: list[StockPriceData] = []
        for record in raw:
            try:
                prices.append(
                    StockPriceData(
                        symbol=f"{record['stock_id']}.TW",
                        market=self.market,
                        date=date.fromisoformat(record["date"]),
                        open=Decimal(str(record["open"])),
                        high=Decimal(str(record["max"])),
                        low=Decimal(str(record["min"])),
                        close=Decimal(str(record["close"])),
                        volume=int(record["Trading_Volume"]),
                        change=Decimal(str(record["spread"])),
                    )
                )
            except (InvalidOperation, ValueError, KeyError) as exc:
                logger.warning(
                    "finmind_skip_invalid_price",
                    stock_id=stock_id,
                    record=record,
                    error=str(exc),
                )
                continue

        return prices
