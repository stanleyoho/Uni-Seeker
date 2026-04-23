from app.modules.price_estimator.base import ValuationEstimate


def estimate_by_pe(
    current_eps: float,
    historical_pe_ratios: list[float],
    current_price: float | None = None,
) -> ValuationEstimate:
    """Estimate price using historical PE range."""
    if not historical_pe_ratios or current_eps <= 0:
        return ValuationEstimate(
            model_name="PE", cheap_price=0, fair_price=0, expensive_price=0,
            confidence=0.0, details={},
        )

    pe_sorted = sorted(historical_pe_ratios)
    n = len(pe_sorted)

    # Use percentiles for cheap/fair/expensive
    low_pe = pe_sorted[int(n * 0.25)] if n >= 4 else pe_sorted[0]
    mid_pe = pe_sorted[int(n * 0.5)]
    high_pe = pe_sorted[int(n * 0.75)] if n >= 4 else pe_sorted[-1]

    confidence = min(n / 20, 1.0)  # more data = more confidence, cap at 1.0

    return ValuationEstimate(
        model_name="PE",
        cheap_price=round(current_eps * low_pe, 2),
        fair_price=round(current_eps * mid_pe, 2),
        expensive_price=round(current_eps * high_pe, 2),
        confidence=round(confidence, 2),
        details={"eps": current_eps, "low_pe": low_pe, "mid_pe": mid_pe, "high_pe": high_pe},
    )
