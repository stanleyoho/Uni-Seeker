"""FinMind provider for market-wide data (stock info, indices, dividends)."""

from __future__ import annotations

from typing import Any

import structlog

from app.config import settings
from app.modules.finmind.client import FinMindClient

logger = structlog.get_logger()


class FinMindMarketProvider:
    """Fetches market-level data from FinMind."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._client = client or FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

    async def fetch_stock_info(self) -> list[dict[str, Any]]:
        """Fetch the full Taiwan stock listing.

        Uses the ``TaiwanStockInfo`` dataset.  No ``data_id`` or date
        range is required.

        Returns
        -------
        list[dict]
            One record per listed security.
        """
        return await self._client.fetch(
            dataset="TaiwanStockInfo",
        )

    async def fetch_index(
        self,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch various market indicators (5-second granularity).

        Uses the ``TaiwanVariousIndicators5Seconds`` dataset.

        Parameters
        ----------
        start_date : str
            ISO start date.

        Returns
        -------
        list[dict]
            Raw indicator records.
        """
        return await self._client.fetch(
            dataset="TaiwanVariousIndicators5Seconds",
            start_date=start_date,
        )

    async def fetch_dividend(
        self,
        stock_id: str,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch dividend distribution data.

        Uses the ``TaiwanStockDividend`` dataset.

        Parameters
        ----------
        stock_id : str
            Taiwan stock symbol (e.g. ``"2330"``).
        start_date : str
            ISO start date.

        Returns
        -------
        list[dict]
            Raw dividend records.
        """
        return await self._client.fetch(
            dataset="TaiwanStockDividend",
            data_id=stock_id,
            start_date=start_date,
        )
