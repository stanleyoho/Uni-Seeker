"""Read Taiwan stock financial statements from the local DB (financial_statements table).

The sync task stores FinMind's `type` code as the field key.
This module maps those codes to yfinance-compatible English names
so the rest of the app (ratios, frontend) works without changes.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_statement import FinancialStatement as FSModel
from app.models.stock import Stock
from app.modules.financial_analysis.base import FinancialData, FinancialStatement

logger = structlog.get_logger()

# ------------------------------------------------------------------ #
# FinMind type code → yfinance-compatible field name                   #
# ------------------------------------------------------------------ #

_INCOME_TYPE_MAP: dict[str, str] = {
    "Revenue": "Total Revenue",
    "CostOfGoodsSold": "Cost Of Revenue",
    "GrossProfit": "Gross Profit",
    "OperatingExpenses": "Operating Expenses",
    "OperatingIncome": "Operating Income",
    "TotalNonoperatingIncomeAndExpense": "Total Other Income Expense Net",
    "PreTaxIncome": "Pretax Income",
    "TAX": "Tax Provision",
    "IncomeAfterTaxes": "Net Income",
    "EquityAttributableToOwnersOfParent": "Net Income Common Stockholders",
    "EPS": "Basic EPS",
}

_BALANCE_TYPE_MAP: dict[str, str] = {
    "TotalAssets": "Total Assets",
    "CurrentAssets": "Current Assets",
    "NoncurrentAssets": "Total Non Current Assets",
    "CashAndCashEquivalents": "Cash And Cash Equivalents",
    "AccountsReceivableNet": "Net Receivables",
    "Inventories": "Inventory",
    "Liabilities": "Total Liabilities Net Minority Interest",
    "CurrentLiabilities": "Current Liabilities",
    "NoncurrentLiabilities": "Total Non Current Liabilities Net Minority Interest",
    "LongtermBorrowings": "Long Term Debt",
    "BondsPayable": "Long Term Debt And Capital Lease Obligation",
    "Equity": "Stockholders Equity",
    "EquityAttributableToOwnersOfParent": "Common Stock Equity",
    "RetainedEarnings": "Retained Earnings",
}

_CASHFLOW_TYPE_MAP: dict[str, str] = {
    "CashFlowsFromOperatingActivities": "Operating Cash Flow",
    "CashProvidedByInvestingActivities": "Investing Cash Flow",
    "PropertyAndPlantAndEquipment": "Capital Expenditure",
    "Depreciation": "Depreciation And Amortization",
    "AmortizationExpense": "Amortization",
}

_STMT_TYPE_MAP: dict[str, dict[str, str]] = {
    "income": _INCOME_TYPE_MAP,
    "balance": _BALANCE_TYPE_MAP,
    "cashflow": _CASHFLOW_TYPE_MAP,
}

_STMT_ORDER = ["income", "balance", "cashflow"]


async def read_tw_financials(symbol: str, db: AsyncSession) -> FinancialData | None:
    """
    Read financial statements from DB for a Taiwan stock.

    Returns None if no data is found (caller should fall back to live fetch).
    """
    # Resolve stock_id
    stock_q = await db.execute(
        select(Stock).where(Stock.symbol == symbol).limit(1)
    )
    stock = stock_q.scalar_one_or_none()

    # Also try with .TW suffix (some stocks stored as "2330.TW")
    if stock is None:
        stock_q = await db.execute(
            select(Stock).where(Stock.symbol == f"{symbol}.TW").limit(1)
        )
        stock = stock_q.scalar_one_or_none()

    if stock is None:
        logger.debug("tw_db_reader_stock_not_found", symbol=symbol)
        return None

    # Fetch all statements, newest first
    rows_q = await db.execute(
        select(FSModel)
        .where(FSModel.stock_id == stock.id)
        .order_by(FSModel.fiscal_year.desc(), FSModel.fiscal_quarter.desc())
    )
    rows: list[FSModel] = list(rows_q.scalars().all())

    if not rows:
        logger.debug("tw_db_reader_no_rows", symbol=symbol)
        return None

    # Group by statement_type → list of FinancialStatement (newest first)
    grouped: dict[str, list[FinancialStatement]] = {t: [] for t in _STMT_ORDER}
    seen_periods: dict[str, set[str]] = {t: set() for t in _STMT_ORDER}

    for row in rows:
        stmt_type = row.statement_type
        if stmt_type not in grouped:
            continue
        if row.period in seen_periods[stmt_type]:
            continue

        field_map = _STMT_TYPE_MAP[stmt_type]
        mapped_data: dict[str, float] = {}

        for raw_key, raw_val in row.data.items():
            # Skip percentage variants (_per suffix)
            if raw_key.endswith("_per"):
                continue
            display_name = field_map.get(raw_key)
            if display_name and display_name not in mapped_data:
                try:
                    mapped_data[display_name] = float(raw_val)
                except (TypeError, ValueError):
                    pass

        if mapped_data:
            grouped[stmt_type].append(
                FinancialStatement(
                    period=row.period,
                    period_type="quarterly",
                    data=mapped_data,
                )
            )
            seen_periods[stmt_type].add(row.period)

    if not grouped["income"]:
        return None

    logger.debug(
        "tw_db_reader_loaded",
        symbol=symbol,
        income=len(grouped["income"]),
        balance=len(grouped["balance"]),
        cashflow=len(grouped["cashflow"]),
    )

    return FinancialData(
        symbol=symbol,
        currency="TWD",
        income_statements=grouped["income"],
        balance_sheets=grouped["balance"],
        cash_flows=grouped["cashflow"],
    )
