"""SEC EDGAR financial data provider for US stocks.

Fetches real 10-K/10-Q XBRL data from data.sec.gov.
No API key required; must include User-Agent header per SEC policy.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from app.modules.financial_analysis.base import FinancialData, FinancialStatement

logger = structlog.get_logger()

_USER_AGENT = "Uni-Seeker stanly7768@gmail.com"
_BASE = "https://data.sec.gov"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Cache ticker → CIK mapping in-process (static SEC file, rarely changes)
_cik_cache: dict[str, str] = {}

# --------------------------------------------------------------------------- #
# XBRL concept → yfinance-compatible field name mappings                       #
# --------------------------------------------------------------------------- #

# Income statement: quarterly flow values (frame = CY{year}Q{n}, no trailing I)
_INCOME_CONCEPTS: list[tuple[str, str]] = [
    # Revenue — try in order, first hit wins
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "Total Revenue"),
    ("Revenues", "Total Revenue"),
    ("RevenueFromContractWithCustomerIncludingAssessedTax", "Total Revenue"),
    # Cost
    ("CostOfGoodsAndServicesSold", "Cost Of Revenue"),
    ("CostOfRevenue", "Cost Of Revenue"),
    ("CostOfGoodsSold", "Cost Of Revenue"),
    # Gross profit
    ("GrossProfit", "Gross Profit"),
    # Operating
    ("OperatingIncomeLoss", "Operating Income"),
    ("ResearchAndDevelopmentExpense", "Research And Development"),
    ("SellingGeneralAndAdministrativeExpense", "Selling General Administrative"),
    # Net income
    ("NetIncomeLoss", "Net Income"),
    # Tax
    ("IncomeTaxExpenseBenefit", "Tax Provision"),
    # EPS
    ("EarningsPerShareBasic", "Basic EPS"),
    ("EarningsPerShareDiluted", "Diluted EPS"),
]

# Balance sheet: instant values (frame = CY{year}Q{n}I or CY{year}I)
_BALANCE_CONCEPTS: list[tuple[str, str]] = [
    ("Assets", "Total Assets"),
    ("AssetsCurrent", "Current Assets"),
    ("AssetsNoncurrent", "Total Non Current Assets"),
    ("CashAndCashEquivalentsAtCarryingValue", "Cash And Cash Equivalents"),
    ("Liabilities", "Total Liabilities Net Minority Interest"),
    ("LiabilitiesCurrent", "Current Liabilities"),
    ("LiabilitiesNoncurrent", "Total Non Current Liabilities Net Minority Interest"),
    ("LongTermDebt", "Long Term Debt"),
    ("StockholdersEquity", "Stockholders Equity"),
    ("RetainedEarningsAccumulatedDeficit", "Retained Earnings"),
    ("AccountsReceivableNetCurrent", "Net Receivables"),
    ("AccountsReceivableNet", "Net Receivables"),
    ("InventoryNet", "Inventory"),
]

# Cash flow: quarterly flow values (frame = CY{year}Q{n}, no trailing I)
_CASHFLOW_CONCEPTS: list[tuple[str, str]] = [
    ("NetCashProvidedByUsedInOperatingActivities", "Operating Cash Flow"),
    ("PaymentsToAcquirePropertyPlantAndEquipment", "Capital Expenditure"),
    ("NetCashProvidedByUsedInInvestingActivities", "Investing Cash Flow"),
    ("NetCashProvidedByUsedInFinancingActivities", "Financing Cash Flow"),
    ("DepreciationDepletionAndAmortization", "Depreciation And Amortization"),
    ("PaymentsForRepurchaseOfCommonStock", "Repurchase Of Capital Stock"),
    ("PaymentsOfDividendsCommonStock", "Common Stock Dividend Paid"),
    ("PaymentsOfDividends", "Common Stock Dividend Paid"),
]

# Quarterly frame patterns
_Q_FLOW_RE = re.compile(r"^CY\d{4}Q[1-4]$")  # income / CF quarterly
_Q_INST_RE = re.compile(r"^CY\d{4}Q[1-4]I$")  # balance sheet quarterly
_Y_FLOW_RE = re.compile(r"^CY\d{4}$")  # income / CF annual
_Y_INST_RE = re.compile(r"^CY\d{4}I$")  # balance sheet annual


class SECEdgarFinancialProvider:
    """Fetches real 10-K/10-Q financial data from SEC EDGAR for US stocks."""

    async def fetch_financials(self, symbol: str) -> FinancialData:
        cik = await self._get_cik(symbol)
        facts = await self._fetch_facts(cik)
        gaap = facts.get("facts", {}).get("us-gaap", {})

        income = self._extract_statements(gaap, _INCOME_CONCEPTS, "flow")
        balance = self._extract_statements(gaap, _BALANCE_CONCEPTS, "instant")
        cashflow = self._extract_statements(gaap, _CASHFLOW_CONCEPTS, "flow")

        return FinancialData(
            symbol=symbol,
            currency="USD",
            income_statements=income,
            balance_sheets=balance,
            cash_flows=cashflow,
        )

    # ------------------------------------------------------------------ #
    # CIK lookup                                                           #
    # ------------------------------------------------------------------ #

    async def _get_cik(self, ticker: str) -> str:
        ticker_upper = ticker.upper()
        if ticker_upper in _cik_cache:
            return _cik_cache[ticker_upper]

        async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(_TICKERS_URL, timeout=15)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        for entry in data.values():
            _cik_cache[entry["ticker"].upper()] = str(entry["cik_str"]).zfill(10)

        if ticker_upper not in _cik_cache:
            raise ValueError(f"Ticker '{ticker}' not found in SEC EDGAR")

        return _cik_cache[ticker_upper]

    # ------------------------------------------------------------------ #
    # Company facts fetch                                                  #
    # ------------------------------------------------------------------ #

    async def _fetch_facts(self, cik: str) -> dict[str, Any]:
        url = f"{_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(url, timeout=30)
            resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    # ------------------------------------------------------------------ #
    # Statement extraction                                                 #
    # ------------------------------------------------------------------ #

    def _extract_statements(
        self,
        gaap: dict[str, Any],
        concepts: list[tuple[str, str]],
        kind: str,  # "flow" or "instant"
    ) -> list[FinancialStatement]:
        """
        Build {period → {field: value}} from XBRL facts.

        kind="flow"    → use quarterly CY{year}Q{n} and annual CY{year} frames
        kind="instant" → use quarterly CY{year}Q{n}I and annual CY{year}I frames
        """
        q_re = _Q_INST_RE if kind == "instant" else _Q_FLOW_RE
        y_re = _Y_INST_RE if kind == "instant" else _Y_FLOW_RE

        # period_end_date → {field_name: value}
        period_data: dict[str, dict[str, float]] = {}
        # period_end_date → period_type
        period_type_map: dict[str, str] = {}

        # Track which field names we've already set per period (first-wins for fallbacks)
        seen_fields: dict[str, set[str]] = {}

        for concept, field_name in concepts:
            if concept not in gaap:
                continue
            units = gaap[concept].get("units", {})
            unit_key = next(iter(units), None)
            if not unit_key:
                continue
            entries: list[dict[str, Any]] = units[unit_key]

            for entry in entries:
                frame = entry.get("frame", "")
                end_date: str = entry.get("end", "")
                if not end_date:
                    continue

                is_quarterly = bool(q_re.match(frame))
                is_annual = bool(y_re.match(frame))
                if not is_quarterly and not is_annual:
                    continue

                period_type = "quarterly" if is_quarterly else "annual"
                val = float(entry["val"])

                if end_date not in period_data:
                    period_data[end_date] = {}
                    seen_fields[end_date] = set()

                # Only set field if not already present (handles fallback chains)
                if field_name not in seen_fields[end_date]:
                    period_data[end_date][field_name] = val
                    seen_fields[end_date].add(field_name)
                    period_type_map[end_date] = period_type

        if not period_data:
            return []

        # Sort descending by date (most recent first), keep last 20 periods
        sorted_dates = sorted(period_data.keys(), reverse=True)[:20]

        statements: list[FinancialStatement] = []
        for date in sorted_dates:
            if not period_data[date]:
                continue
            statements.append(
                FinancialStatement(
                    period=date,
                    period_type=period_type_map.get(date, "quarterly"),
                    data=period_data[date],
                )
            )

        return statements
