import asyncio
from decimal import Decimal
from functools import partial

import structlog
import yfinance as yf

from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()

EXCHANGE_MAP: dict[str, str] = {
    "NMS": "US_NASDAQ",
    "NGM": "US_NASDAQ",
    "NCM": "US_NASDAQ",
    "NYQ": "US_NYSE",
    "PCX": "US_NYSE",
    "ASE": "US_NYSE",
}


class YFinanceProvider:
    """Fetches daily stock prices from Yahoo Finance (US stocks)."""

    @property
    def market(self) -> str:
        return "US_NASDAQ"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        if symbol is None:
            logger.warning("yfinance_requires_symbol")
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, symbol))

    def _fetch_sync(self, symbol: str) -> list[StockPriceData]:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            return []

        exchange = ticker.info.get("exchange", "NMS") if hasattr(ticker, "info") else "NMS"
        market = EXCHANGE_MAP.get(exchange, "US_NASDAQ")

        prices: list[StockPriceData] = []
        for dt, row in hist.iterrows():
            prices.append(
                StockPriceData(
                    symbol=symbol,
                    market=market,
                    date=dt.date() if hasattr(dt, "date") else dt,
                    open=Decimal(str(round(row["Open"], 4))),
                    high=Decimal(str(round(row["High"], 4))),
                    low=Decimal(str(round(row["Low"], 4))),
                    close=Decimal(str(round(row["Close"], 4))),
                    volume=int(row["Volume"]),
                )
            )
        return prices
