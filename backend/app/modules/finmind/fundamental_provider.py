"""FinMind provider for fundamental / financial statement data."""

from __future__ import annotations

from typing import Any

import structlog

from app.config import settings
from app.modules.finmind.client import FinMindClient

logger = structlog.get_logger()


class FinMindFundamentalProvider:
    """Fetches PER/PBR, revenue, and financial statements from FinMind."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._client = client or FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

    async def fetch_per_pbr(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch PER / PBR / dividend yield data.

        Uses the ``TaiwanStockPER`` dataset.
        """
        return await self._client.fetch(
            dataset="TaiwanStockPER",
            data_id=stock_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def fetch_revenue(
        self,
        stock_id: str,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch monthly revenue data.

        Uses the ``TaiwanStockMonthRevenue`` dataset.
        """
        return await self._client.fetch(
            dataset="TaiwanStockMonthRevenue",
            data_id=stock_id,
            start_date=start_date,
        )

    async def fetch_income_statement(
        self,
        stock_id: str,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch income statement data.

        Uses the ``TaiwanStockFinancialStatements`` dataset.
        """
        return await self._client.fetch(
            dataset="TaiwanStockFinancialStatements",
            data_id=stock_id,
            start_date=start_date,
        )

    async def fetch_balance_sheet(
        self,
        stock_id: str,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch balance sheet data.

        Uses the ``TaiwanStockBalanceSheet`` dataset.
        """
        return await self._client.fetch(
            dataset="TaiwanStockBalanceSheet",
            data_id=stock_id,
            start_date=start_date,
        )

    async def fetch_cash_flow(
        self,
        stock_id: str,
        start_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch cash flow statement data.

        Uses the ``TaiwanStockCashFlowsStatement`` dataset.
        """
        return await self._client.fetch(
            dataset="TaiwanStockCashFlowsStatement",
            data_id=stock_id,
            start_date=start_date,
        )
