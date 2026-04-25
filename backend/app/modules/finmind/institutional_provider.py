"""FinMind provider for institutional investor and shareholding data."""

from __future__ import annotations

from typing import Any

import structlog

from app.config import settings
from app.modules.finmind.client import FinMindClient

logger = structlog.get_logger()


class FinMindInstitutionalProvider:
    """Fetches institutional buy/sell and shareholding data from FinMind."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._client = client or FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

    async def fetch_institutional(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch institutional investors buy/sell data.

        Uses the ``TaiwanStockInstitutionalInvestorsBuySell`` dataset.

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
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def fetch_shareholding(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch shareholding distribution data.

        Uses the ``TaiwanStockShareholding`` dataset.

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
            dataset="TaiwanStockShareholding",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )
