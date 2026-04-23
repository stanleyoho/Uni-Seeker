import asyncio
from functools import partial

import yfinance as yf
import structlog
import pandas as pd

from app.modules.financial_analysis.base import FinancialData, FinancialStatement

logger = structlog.get_logger()


class YFinanceFinancialProvider:
    async def fetch_financials(self, symbol: str) -> FinancialData:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, symbol))

    def _fetch_sync(self, symbol: str) -> FinancialData:
        ticker = yf.Ticker(symbol)
        currency = ticker.info.get("currency", "USD") if hasattr(ticker, "info") else "USD"

        income = self._parse_statements(ticker.quarterly_income_stmt, "quarterly")
        balance = self._parse_statements(ticker.quarterly_balance_sheet, "quarterly")
        cashflow = self._parse_statements(ticker.quarterly_cashflow, "quarterly")

        # Also get annual
        income += self._parse_statements(ticker.income_stmt, "annual")
        balance += self._parse_statements(ticker.balance_sheet, "annual")
        cashflow += self._parse_statements(ticker.cashflow, "annual")

        return FinancialData(
            symbol=symbol,
            currency=currency,
            income_statements=income,
            balance_sheets=balance,
            cash_flows=cashflow,
        )

    def _parse_statements(self, df: pd.DataFrame, period_type: str) -> list[FinancialStatement]:
        if df is None or df.empty:
            return []

        statements: list[FinancialStatement] = []
        for col in df.columns:
            period_label = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            data: dict[str, float] = {}
            for idx in df.index:
                val = df.loc[idx, col]
                if pd.notna(val):
                    data[str(idx)] = float(val)
            if data:
                statements.append(FinancialStatement(
                    period=period_label, period_type=period_type, data=data,
                ))
        return statements
