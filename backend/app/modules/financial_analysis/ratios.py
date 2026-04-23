from dataclasses import dataclass

from app.modules.financial_analysis.base import FinancialData


@dataclass
class FinancialRatios:
    """Calculated financial ratios for a stock."""
    symbol: str
    period: str
    # Profitability
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    # Efficiency
    inventory_turnover: float | None = None
    receivable_turnover: float | None = None
    # Leverage
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_ratio: float | None = None
    # Growth (YoY)
    revenue_growth: float | None = None
    net_income_growth: float | None = None


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 4)


def calculate_ratios(data: FinancialData) -> list[FinancialRatios]:
    """Calculate financial ratios from financial statements."""
    results: list[FinancialRatios] = []

    for i, income in enumerate(data.income_statements):
        # Find matching balance sheet and cash flow by period
        balance = data.balance_sheets[i] if i < len(data.balance_sheets) else None

        d = income.data
        bd = balance.data if balance else {}

        total_revenue = d.get("Total Revenue") or d.get("TotalRevenue")
        cost_of_revenue = d.get("Cost Of Revenue") or d.get("CostOfRevenue")
        operating_income = d.get("Operating Income") or d.get("OperatingIncome")
        net_income = d.get("Net Income") or d.get("NetIncome")

        total_assets = bd.get("Total Assets") or bd.get("TotalAssets")
        total_equity = (
            bd.get("Stockholders Equity")
            or bd.get("StockholdersEquity")
            or bd.get("Total Equity Gross Minority Interest")
        )
        total_liabilities = (
            bd.get("Total Liabilities Net Minority Interest")
            or bd.get("TotalLiabilitiesNetMinorityInterest")
        )
        current_assets = bd.get("Current Assets") or bd.get("CurrentAssets")
        current_liabilities = bd.get("Current Liabilities") or bd.get("CurrentLiabilities")
        inventory = bd.get("Inventory")
        receivables = bd.get("Net Receivables") or bd.get("Receivables")

        gross_profit = (total_revenue - cost_of_revenue) if total_revenue and cost_of_revenue else None

        ratios = FinancialRatios(
            symbol=data.symbol,
            period=income.period,
            gross_margin=_safe_div(gross_profit, total_revenue),
            operating_margin=_safe_div(operating_income, total_revenue),
            net_margin=_safe_div(net_income, total_revenue),
            roe=_safe_div(net_income, total_equity),
            roa=_safe_div(net_income, total_assets),
            current_ratio=_safe_div(current_assets, current_liabilities),
            quick_ratio=_safe_div(
                (current_assets - inventory) if current_assets and inventory else None,
                current_liabilities,
            ),
            debt_ratio=_safe_div(total_liabilities, total_assets),
            inventory_turnover=_safe_div(cost_of_revenue, inventory),
            receivable_turnover=_safe_div(total_revenue, receivables),
        )

        # YoY growth: compare with statement from same period type, 4 periods back (quarterly) or 1 back (annual)
        compare_idx = i + (4 if income.period_type == "quarterly" else 1)
        if compare_idx < len(data.income_statements):
            prev = data.income_statements[compare_idx].data
            prev_revenue = prev.get("Total Revenue") or prev.get("TotalRevenue")
            prev_net = prev.get("Net Income") or prev.get("NetIncome")
            ratios.revenue_growth = _safe_div(
                (total_revenue - prev_revenue) if total_revenue and prev_revenue else None,
                abs(prev_revenue) if prev_revenue else None,
            )
            ratios.net_income_growth = _safe_div(
                (net_income - prev_net) if net_income and prev_net else None,
                abs(prev_net) if prev_net else None,
            )

        results.append(ratios)

    return results
