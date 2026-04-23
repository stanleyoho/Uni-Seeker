from app.modules.price_estimator.base import ValuationEstimate
from app.modules.price_estimator.composite import composite_estimate

def test_composite_weighted_average() -> None:
    estimates = [
        ValuationEstimate("PE", 80, 100, 120, 0.8, {}),
        ValuationEstimate("DDM", 70, 90, 110, 0.6, {}),
    ]
    result = composite_estimate(estimates)
    assert result.model_name == "Composite"
    assert 85 < result.fair_price < 100  # weighted toward PE (higher confidence)

def test_composite_ignores_zero_confidence() -> None:
    estimates = [
        ValuationEstimate("PE", 80, 100, 120, 0.8, {}),
        ValuationEstimate("DDM", 0, 0, 0, 0.0, {}),
    ]
    result = composite_estimate(estimates)
    assert result.fair_price == 100  # only PE used

def test_composite_all_zero() -> None:
    estimates = [
        ValuationEstimate("PE", 0, 0, 0, 0.0, {}),
    ]
    result = composite_estimate(estimates)
    assert result.confidence == 0.0
