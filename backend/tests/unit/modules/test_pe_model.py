from app.modules.price_estimator.pe_model import estimate_by_pe

def test_pe_basic() -> None:
    result = estimate_by_pe(current_eps=10.0, historical_pe_ratios=[10, 12, 15, 18, 20])
    assert result.cheap_price > 0
    assert result.cheap_price < result.fair_price < result.expensive_price

def test_pe_negative_eps() -> None:
    result = estimate_by_pe(current_eps=-5.0, historical_pe_ratios=[10, 15, 20])
    assert result.confidence == 0.0

def test_pe_empty_history() -> None:
    result = estimate_by_pe(current_eps=10.0, historical_pe_ratios=[])
    assert result.confidence == 0.0

def test_pe_confidence_scales_with_data() -> None:
    short = estimate_by_pe(current_eps=10.0, historical_pe_ratios=[15])
    long = estimate_by_pe(current_eps=10.0, historical_pe_ratios=[10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30])
    assert long.confidence > short.confidence
