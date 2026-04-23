import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.price_updater.base import DataProvider, StockPriceData

logger = structlog.get_logger()

MARKET_MAP: dict[str, Market] = {
    "TW_TWSE": Market.TW_TWSE,
    "TW_TPEX": Market.TW_TPEX,
    "US_NYSE": Market.US_NYSE,
    "US_NASDAQ": Market.US_NASDAQ,
}


@dataclass
class UpdateResult:
    total_fetched: int = 0
    duplicates_skipped: int = 0
    invalid_skipped: int = 0
    saved: int = 0
    errors: list[str] = field(default_factory=list)


class PriceUpdater:
    def __init__(
        self,
        providers: list[DataProvider],
        session: AsyncSession,
        max_retries: int = 3,
        retry_delay: float = 0.0,
    ) -> None:
        self._providers = providers
        self._session = session
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def update_all(self, symbol: str | None = None) -> UpdateResult:
        result = UpdateResult()
        all_prices: list[StockPriceData] = []

        for provider in self._providers:
            prices = await self._fetch_with_retry(provider, symbol, result)
            all_prices.extend(prices)

        result.total_fetched = len(all_prices)

        seen: set[tuple[str, object]] = set()
        unique_prices: list[StockPriceData] = []
        for price in all_prices:
            key = (price.symbol, price.date)
            if key in seen:
                result.duplicates_skipped += 1
                continue
            seen.add(key)

            if price.close <= Decimal("0"):
                result.invalid_skipped += 1
                logger.warning("invalid_price", symbol=price.symbol, close=price.close)
                continue

            unique_prices.append(price)

        # Persist to database
        await self._persist_prices(unique_prices)
        await self._persist_stocks(unique_prices)

        result.saved = len(unique_prices)
        return result

    async def _persist_prices(self, prices: list[StockPriceData]) -> None:
        """Upsert prices into stock_prices table."""
        if not prices:
            return

        for batch_start in range(0, len(prices), 500):
            batch = prices[batch_start : batch_start + 500]
            values = [
                {
                    "symbol": p.symbol,
                    "market": MARKET_MAP.get(p.market, Market.TW_TWSE),
                    "date": p.date,
                    "open": p.open,
                    "high": p.high,
                    "low": p.low,
                    "close": p.close,
                    "volume": p.volume,
                    "change": p.change,
                    "change_percent": p.change_percent,
                }
                for p in batch
            ]
            stmt = pg_insert(StockPrice).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_symbol_date",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "change": stmt.excluded.change,
                    "change_percent": stmt.excluded.change_percent,
                },
            )
            await self._session.execute(stmt)

        await self._session.commit()
        logger.info("prices_persisted", count=len(prices))

    async def _persist_stocks(self, prices: list[StockPriceData]) -> None:
        """Upsert stocks into stocks table (for search)."""
        if not prices:
            return

        seen_symbols: set[str] = set()
        stock_data: list[dict[str, object]] = []
        for p in prices:
            if p.symbol in seen_symbols:
                continue
            seen_symbols.add(p.symbol)
            stock_data.append({
                "symbol": p.symbol,
                "name": p.name or p.symbol,
                "market": MARKET_MAP.get(p.market, Market.TW_TWSE),
            })

        for batch_start in range(0, len(stock_data), 500):
            batch = stock_data[batch_start : batch_start + 500]
            stmt = pg_insert(Stock).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={"name": stmt.excluded.name},
            )
            await self._session.execute(stmt)

        await self._session.commit()
        logger.info("stocks_persisted", count=len(stock_data))

    async def _fetch_with_retry(
        self,
        provider: DataProvider,
        symbol: str | None,
        result: UpdateResult,
    ) -> list[StockPriceData]:
        for attempt in range(self._max_retries):
            try:
                return await provider.fetch_daily_prices(symbol)
            except Exception as e:
                logger.warning(
                    "fetch_failed",
                    provider=provider.market,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < self._max_retries - 1 and self._retry_delay > 0:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))

        result.errors.append(f"{provider.market}: failed after {self._max_retries} retries")
        return []
