import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

import structlog

from app.modules.price_updater.base import DataProvider, StockPriceData

logger = structlog.get_logger()


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
        session: object,
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

        result.saved = len(unique_prices)
        return result

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
