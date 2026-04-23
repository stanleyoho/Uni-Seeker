from app.modules.price_estimator.ddm import estimate_by_ddm

def test_ddm_basic() -> None:
    result = estimate_by_ddm(annual_dividend=5.0, growth_rate=0.03)
    assert result.fair_price > 0
    assert result.cheap_price < result.fair_price < result.expensive_price

def test_ddm_no_dividend() -> None:
    result = estimate_by_ddm(annual_dividend=0.0)
    assert result.confidence == 0.0

def test_ddm_growth_exceeds_discount() -> None:
    result = estimate_by_ddm(annual_dividend=5.0, growth_rate=0.15)
    assert result.confidence == 0.0
