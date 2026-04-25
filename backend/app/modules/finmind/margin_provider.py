"""FinMind provider for margin trading (融資融券) data."""

from __future__ import annotations

from typing import Any

import structlog

from app.config import settings
from app.modules.finmind.client import FinMindClient

logger = structlog.get_logger()


class FinMindMarginProvider:
    """Fetches margin purchase / short sale data from FinMind."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._client = client or FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

    async def fetch_margin(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch margin purchase and short sale records.

        Uses the ``TaiwanStockMarginPurchaseShortSale`` dataset.

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
        list[dict]
            Raw records from FinMind.
        """
        return await self._client.fetch(
            dataset="TaiwanStockMarginPurchaseShortSale",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )
