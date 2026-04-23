from __future__ import annotations

import httpx
import structlog

from app.modules.revenue.base import RevenueRecord

logger = structlog.get_logger()

TWSE_MONTHLY_REVENUE = "/opendata/t187ap05_L"


class TWSERevenueProvider:
    """Fetch official monthly revenue from TWSE open-data API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://openapi.twse.com.tw/v1",
    ) -> None:
        self._client = client
        self._base_url = base_url

    async def fetch_all_revenue(self) -> list[RevenueRecord]:
        """Fetch latest monthly revenue for all listed companies."""
        url = f"{self._base_url}{TWSE_MONTHLY_REVENUE}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw: list[dict[str, str]] = response.json()

        records: list[RevenueRecord] = []
        for item in raw:
            code = item.get("公司代號", "").strip()
            if not code:
                continue

            # Parse ROC date: "11503" -> 2026-03
            ym = item.get("資料年月", "")
            try:
                roc_year = int(ym[:-2])
                month = int(ym[-2:])
                western_year = roc_year + 1911
                period = f"{western_year}-{month:02d}"
            except (ValueError, IndexError):
                continue

            # Revenue in thousands (仟元)
            try:
                revenue = float(item.get("營業收入-當月營收", "0"))
                _prev_month = float(item.get("營業收入-上月營收", "0"))
                _prev_year = float(item.get("營業收入-去年當月營收", "0"))
            except ValueError:
                continue

            # Growth rates
            try:
                mom_growth = float(item.get("營業收入-上月比較增減(%)", "0"))
            except ValueError:
                mom_growth = 0.0
            try:
                yoy_growth = float(item.get("營業收入-去年同月增減(%)", "0"))
            except ValueError:
                yoy_growth = 0.0

            records.append(
                RevenueRecord(
                    symbol=f"{code}.TW",
                    period=period,
                    period_type="monthly",
                    revenue=revenue,
                    currency="TWD",
                    mom_growth=mom_growth,
                    yoy_growth=yoy_growth,
                    industry=item.get("產業別", ""),
                )
            )

        logger.info("twse_revenue_fetched", count=len(records))
        return records
