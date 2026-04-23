from app.modules.financial_analysis.base import FinancialData, FinancialStatement
from app.modules.financial_analysis.ratios import calculate_ratios


def _make_financial_data() -> FinancialData:
    income = [
        FinancialStatement(period="2024-12-31", period_type="quarterly", data={
            "Total Revenue": 1000000, "Cost Of Revenue": 600000,
            "Operating Income": 200000, "Net Income": 150000,
        }),
        FinancialStatement(period="2024-09-30", period_type="quarterly", data={
            "Total Revenue": 950000, "Cost Of Revenue": 580000,
            "Operating Income": 180000, "Net Income": 140000,
        }),
    ]
    balance = [
        FinancialStatement(period="2024-12-31", period_type="quarterly", data={
            "Total Assets": 5000000, "Current Assets": 2000000,
            "Current Liabilities": 1500000, "Stockholders Equity": 3000000,
            "Total Liabilities Net Minority Interest": 2000000,
            "Inventory": 500000, "Net Receivables": 800000,
        }),
    ]
    return FinancialData(symbol="TEST", currency="USD",
                         income_statements=income, balance_sheets=balance)


def test_profitability_ratios() -> None:
    ratios = calculate_ratios(_make_financial_data())
    r = ratios[0]
    assert r.gross_margin == 0.4  # (1M - 600K) / 1M
    assert r.operating_margin == 0.2  # 200K / 1M
    assert r.net_margin == 0.15  # 150K / 1M
    assert r.roe == 0.05  # 150K / 3M


def test_leverage_ratios() -> None:
    ratios = calculate_ratios(_make_financial_data())
    r = ratios[0]
    assert r.current_ratio is not None
    assert abs(r.current_ratio - 1.3333) < 0.01  # 2M / 1.5M
    assert r.debt_ratio == 0.4  # 2M / 5M


def test_empty_data_returns_empty() -> None:
    data = FinancialData(symbol="X", currency="USD")
    assert calculate_ratios(data) == []
