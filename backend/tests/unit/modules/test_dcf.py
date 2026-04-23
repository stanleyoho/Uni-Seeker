from app.modules.price_estimator.dcf import estimate_by_dcf

def test_dcf_basic() -> None:
    result = estimate_by_dcf(free_cash_flow=1_000_000, shares_outstanding=100_000)
    assert result.fair_price > 0
    assert result.cheap_price < result.fair_price < result.expensive_price

def test_dcf_negative_fcf() -> None:
    result = estimate_by_dcf(free_cash_flow=-500_000, shares_outstanding=100_000)
    assert result.confidence == 0.0

def test_dcf_discount_rate_below_terminal_growth() -> None:
    result = estimate_by_dcf(free_cash_flow=1_000_000, shares_outstanding=100_000, discount_rate=0.01, terminal_growth=0.02)
    assert result.confidence == 0.0

def test_dcf_margin_of_safety() -> None:
    result = estimate_by_dcf(free_cash_flow=1_000_000, shares_outstanding=100_000)
    assert result.cheap_price == round(result.fair_price * 0.7, 2)
    assert result.expensive_price == round(result.fair_price * 1.3, 2)
