from app.modules.financial_analysis.ratios import FinancialRatios
from app.modules.financial_analysis.scorer import calculate_health_score


def test_healthy_company() -> None:
    ratios = FinancialRatios(
        symbol="GOOD", period="2024Q4",
        gross_margin=0.45, operating_margin=0.25, net_margin=0.18,
        roe=0.22, roa=0.12,
        inventory_turnover=8.0, receivable_turnover=10.0,
        current_ratio=2.5, quick_ratio=1.8, debt_ratio=0.25,
        revenue_growth=0.15, net_income_growth=0.20,
    )
    score = calculate_health_score(ratios)
    assert score.total_score > 70
    assert score.profitability_score > 15


def test_struggling_company() -> None:
    ratios = FinancialRatios(
        symbol="BAD", period="2024Q4",
        gross_margin=0.05, operating_margin=-0.05, net_margin=-0.1,
        roe=-0.05, roa=-0.02,
        inventory_turnover=1.5, receivable_turnover=2.5,
        current_ratio=0.6, quick_ratio=0.3, debt_ratio=0.75,
        revenue_growth=-0.15, net_income_growth=-0.3,
        )
    score = calculate_health_score(ratios)
    assert score.total_score < 30


def test_score_between_0_and_100() -> None:
    ratios = FinancialRatios(symbol="X", period="Q1")
    score = calculate_health_score(ratios)
    assert 0 <= score.total_score <= 100
