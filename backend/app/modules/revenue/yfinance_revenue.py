import asyncio
from functools import partial

import yfinance as yf
import pandas as pd
import structlog

from app.modules.revenue.base import RevenueRecord

logger = structlog.get_logger()


class YFinanceRevenueProvider:
    async def fetch_revenue(self, symbol: str) -> list[RevenueRecord]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, symbol))

    def _fetch_sync(self, symbol: str) -> list[RevenueRecord]:
        ticker = yf.Ticker(symbol)
        currency = ticker.info.get("currency", "TWD") if hasattr(ticker, "info") else "TWD"
        records: list[RevenueRecord] = []

        # Quarterly revenue from income statement
        stmt = ticker.quarterly_income_stmt
        if stmt is not None and not stmt.empty:
            for col in stmt.columns:
                revenue_val = None
                for key in ["Total Revenue", "TotalRevenue", "Revenue"]:
                    if key in stmt.index:
                        val = stmt.loc[key, col]
                        if pd.notna(val):
                            revenue_val = float(val)
                            break

                if revenue_val is not None:
                    period_str = col.strftime("%Y-Q%q") if hasattr(col, "strftime") else str(col)
                    # Fix quarter formatting
                    if hasattr(col, "month"):
                        q = (col.month - 1) // 3 + 1
                        period_str = f"{col.year}-Q{q}"

                    records.append(RevenueRecord(
                        symbol=symbol, period=period_str,
                        period_type="quarterly", revenue=revenue_val, currency=currency,
                    ))

        # Sort by period descending
        records.sort(key=lambda r: r.period, reverse=True)
        return records
