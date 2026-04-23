from app.modules.price_estimator.base import ValuationEstimate


def estimate_by_ddm(
    annual_dividend: float,
    growth_rate: float = 0.03,
    discount_rates: tuple[float, float, float] = (0.08, 0.10, 0.12),
) -> ValuationEstimate:
    """Gordon Growth Model: P = D / (r - g)"""
    if annual_dividend <= 0 or growth_rate >= min(discount_rates):
        return ValuationEstimate(
            model_name="DDM", cheap_price=0, fair_price=0, expensive_price=0,
            confidence=0.0, details={},
        )

    low_r, mid_r, high_r = discount_rates
    # Higher discount rate = lower price (more conservative = cheap)
    expensive = round(annual_dividend / (low_r - growth_rate), 2)
    fair = round(annual_dividend / (mid_r - growth_rate), 2)
    cheap = round(annual_dividend / (high_r - growth_rate), 2)

    confidence = 0.6 if annual_dividend > 0 else 0.0

    return ValuationEstimate(
        model_name="DDM",
        cheap_price=cheap,
        fair_price=fair,
        expensive_price=expensive,
        confidence=confidence,
        details={
            "dividend": annual_dividend, "growth_rate": growth_rate,
            "discount_rates": {"low": low_r, "mid": mid_r, "high": high_r},
        },
    )
