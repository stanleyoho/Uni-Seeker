"""FinMind financial data provider for Taiwan stocks.

Fetches real MOPS-sourced quarterly financial statements via FinMind API.
Data format: [{date, stock_id, type, value, origin_name}, ...]
"""

from __future__ import annotations

from typing import Any

import structlog

from app.modules.financial_analysis.base import FinancialData, FinancialStatement
from app.modules.finmind.client import FinMindClient
from app.modules.finmind.fundamental_provider import FinMindFundamentalProvider

logger = structlog.get_logger()

_START_DATE = "2018-01-01"

# FinMind origin_name (Chinese MOPS field name) → yfinance-compatible English name
# Income statement
_INCOME_MAP: dict[str, str] = {
    "營業收入合計": "Total Revenue",
    "營業收入": "Total Revenue",
    "營業成本": "Cost Of Revenue",
    "營業毛利（毛損）": "Gross Profit",
    "營業毛利(毛損)": "Gross Profit",
    "營業利益（損失）": "Operating Income",
    "營業利益(損失)": "Operating Income",
    "本期淨利（淨損）": "Net Income",
    "本期淨利(淨損)": "Net Income",
    "繼續營業單位稅前淨利（淨損）": "Pretax Income",
    "所得稅費用（利益）": "Tax Provision",
    "研究發展費用": "Research And Development",
    "推銷費用": "Selling Expense",
    "管理費用": "General And Administrative Expense",
    "基本每股盈餘（元）": "Basic EPS",
    "稀釋每股盈餘（元）": "Diluted EPS",
}

# Balance sheet
_BALANCE_MAP: dict[str, str] = {
    "資產總計": "Total Assets",
    "流動資產合計": "Current Assets",
    "非流動資產合計": "Total Non Current Assets",
    "現金及約當現金": "Cash And Cash Equivalents",
    "應收帳款": "Net Receivables",
    "存貨": "Inventory",
    "負債總計": "Total Liabilities Net Minority Interest",
    "流動負債合計": "Current Liabilities",
    "非流動負債合計": "Total Non Current Liabilities Net Minority Interest",
    "長期借款": "Long Term Debt",
    "權益總計": "Stockholders Equity",
    "保留盈餘（累積虧損）": "Retained Earnings",
    "保留盈餘(累積虧損)": "Retained Earnings",
}

# Cash flow
_CASHFLOW_MAP: dict[str, str] = {
    "營業活動之淨現金流入（流出）": "Operating Cash Flow",
    "營業活動之淨現金流入(流出)": "Operating Cash Flow",
    "投資活動之淨現金流入（流出）": "Investing Cash Flow",
    "投資活動之淨現金流入(流出)": "Investing Cash Flow",
    "籌資活動之淨現金流入（流出）": "Financing Cash Flow",
    "籌資活動之淨現金流入(流出)": "Financing Cash Flow",
    "購置不動產、廠房及設備": "Capital Expenditure",
    "不動產廠房及設備之取得": "Capital Expenditure",
    "折舊費用": "Depreciation And Amortization",
    "折舊及攤銷": "Depreciation And Amortization",
}


class FinMindTWFinancialProvider:
    """Fetches real quarterly financial data from FinMind for Taiwan stocks."""

    def __init__(self, client: FinMindClient | None = None) -> None:
        self._provider = FinMindFundamentalProvider(client)

    async def fetch_financials(self, symbol: str) -> FinancialData:
        # Fetch all three statement types concurrently
        import asyncio

        income_raw, balance_raw, cashflow_raw = await asyncio.gather(
            self._provider.fetch_income_statement(symbol, _START_DATE),
            self._provider.fetch_balance_sheet(symbol, _START_DATE),
            self._provider.fetch_cash_flow(symbol, _START_DATE),
        )

        income = self._parse_statements(income_raw, _INCOME_MAP)
        balance = self._parse_statements(balance_raw, _BALANCE_MAP)
        cashflow = self._parse_statements(cashflow_raw, _CASHFLOW_MAP)

        return FinancialData(
            symbol=symbol,
            currency="TWD",
            income_statements=income,
            balance_sheets=balance,
            cash_flows=cashflow,
        )

    def _parse_statements(
        self,
        rows: list[dict[str, Any]],
        field_map: dict[str, str],
    ) -> list[FinancialStatement]:
        """
        Convert FinMind row list to FinancialStatement list.

        Each row: {date, stock_id, type, value, origin_name}
        Group by date → one FinancialStatement per period.
        """
        # date → {field_name: value}
        period_data: dict[str, dict[str, float]] = {}
        # Track first-seen per (date, field_name) to handle duplicate origin_names
        seen: dict[str, set[str]] = {}

        for row in rows:
            date: str = row.get("date", "")
            origin_name: str = row.get("origin_name", "")
            value = row.get("value")
            if not date or value is None:
                continue

            field_name = field_map.get(origin_name)
            if not field_name:
                continue

            try:
                val = float(value)
            except (TypeError, ValueError):
                continue

            if date not in period_data:
                period_data[date] = {}
                seen[date] = set()

            if field_name not in seen[date]:
                period_data[date][field_name] = val
                seen[date].add(field_name)

        if not period_data:
            return []

        sorted_dates = sorted(period_data.keys(), reverse=True)[:20]

        statements: list[FinancialStatement] = []
        for date in sorted_dates:
            if not period_data[date]:
                continue
            statements.append(
                FinancialStatement(
                    period=date,
                    period_type="quarterly",
                    data=period_data[date],
                )
            )

        return statements
