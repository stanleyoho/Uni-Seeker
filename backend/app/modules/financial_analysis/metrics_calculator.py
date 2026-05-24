"""Financial metrics calculator.

Computes ratios from FinMind financial statement data (stored as JSONB dicts).
FinMind uses type names like: Revenue, GrossProfit, OperatingIncome, IncomeAfterTaxes,
TotalAssets, CurrentAssets, CurrentLiabilities, TotalLiabilities, Equity, Inventory,
CashFlowsFromOperatingActivities, CashFlowsFromInvestingActivities, EPS, etc.
"""

from __future__ import annotations


def _safe_div(a: float | None, b: float | None) -> float | None:
    """Safe division returning None if either operand is None or divisor is 0."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _safe_pct(a: float | None, b: float | None) -> float | None:
    """Safe percentage: (a/b) * 100."""
    r = _safe_div(a, b)
    return round(r * 100, 2) if r is not None else None


def deaccumulate(
    current_cum: dict[str, float],
    prev_cum: dict[str, float] | None,
    quarter: int,
) -> dict[str, float]:
    """Convert cumulative IFRS data to single-quarter.

    Q1 is already single quarter. Q2/Q3/Q4 need subtraction.
    Balance sheet items are point-in-time (no deaccumulation needed).
    """
    if quarter == 1 or prev_cum is None:
        return current_cum

    # Income statement and cash flow items need deaccumulation
    # Balance sheet items (Assets, Liabilities, Equity) are point-in-time
    POINT_IN_TIME = {
        "TotalAssets",
        "CurrentAssets",
        "NonCurrentAssets",
        "TotalLiabilities",
        "CurrentLiabilities",
        "NonCurrentLiabilities",
        "Equity",
        "Inventory",
        "AccountsReceivableNet",
        "AccountsPayable",
        "RetainedEarnings",
        "NumberOfSharesIssued",
    }

    result = {}
    for key, val in current_cum.items():
        if key in POINT_IN_TIME:
            result[key] = val
        else:
            prev_val = prev_cum.get(key, 0)
            result[key] = val - prev_val
    return result


def compute_metrics(
    income: dict[str, float],
    balance: dict[str, float],
    cashflow: dict[str, float],
    prev_year_income: dict[str, float] | None = None,
) -> dict[str, float | None]:
    """Compute financial metrics from single-quarter statement data.

    Args:
        income: Income statement data {type: value}
        balance: Balance sheet data {type: value}
        cashflow: Cash flow statement data {type: value}
        prev_year_income: Same quarter last year's income (for YoY growth)
    """
    revenue = income.get("Revenue")
    gross_profit = income.get("GrossProfit")
    operating_income = income.get("OperatingIncome")
    net_income = income.get("IncomeAfterTaxes")
    eps = income.get("EPS")

    total_assets = balance.get("TotalAssets")
    current_assets = balance.get("CurrentAssets")
    current_liabilities = balance.get("CurrentLiabilities")
    total_liabilities = balance.get("TotalLiabilities")
    equity = balance.get("Equity")
    inventory = balance.get("Inventory", 0)

    op_cf = cashflow.get("CashFlowsFromOperatingActivities")
    inv_cf = cashflow.get("CashFlowsFromInvestingActivities")

    metrics: dict[str, float | None] = {
        "gross_margin": _safe_pct(gross_profit, revenue),
        "operating_margin": _safe_pct(operating_income, revenue),
        "net_margin": _safe_pct(net_income, revenue),
        "roe": _safe_pct(net_income, equity),
        "roa": _safe_pct(net_income, total_assets),
        "asset_turnover": _safe_div(revenue, total_assets),
        "debt_to_equity": _safe_div(total_liabilities, equity),
        "current_ratio": _safe_div(current_assets, current_liabilities),
        "quick_ratio": _safe_div(
            (current_assets - inventory)
            if current_assets is not None and inventory is not None
            else None,
            current_liabilities,
        ),
        "eps": eps,
        "fcf": (op_cf + inv_cf) if op_cf is not None and inv_cf is not None else None,
        "operating_cf_ratio": _safe_div(op_cf, net_income),
    }

    # YoY growth
    if prev_year_income:
        prev_rev = prev_year_income.get("Revenue")
        prev_eps = prev_year_income.get("EPS")
        prev_op = prev_year_income.get("OperatingIncome")

        metrics["revenue_growth_yoy"] = _safe_pct(
            (revenue - prev_rev) if revenue is not None and prev_rev is not None else None,
            abs(prev_rev) if prev_rev else None,
        )
        metrics["eps_growth_yoy"] = _safe_pct(
            (eps - prev_eps) if eps is not None and prev_eps is not None else None,
            abs(prev_eps) if prev_eps else None,
        )
        metrics["operating_income_growth_yoy"] = _safe_pct(
            (operating_income - prev_op)
            if operating_income is not None and prev_op is not None
            else None,
            abs(prev_op) if prev_op else None,
        )
    else:
        metrics["revenue_growth_yoy"] = None
        metrics["eps_growth_yoy"] = None
        metrics["operating_income_growth_yoy"] = None

    return metrics
