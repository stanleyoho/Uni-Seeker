from app.modules.price_estimator.base import ValuationEstimate


def estimate_by_dcf(
    free_cash_flow: float,
    growth_rate: float = 0.05,
    terminal_growth: float = 0.02,
    discount_rate: float = 0.10,
    shares_outstanding: float = 1.0,
    projection_years: int = 5,
) -> ValuationEstimate:
    """Simplified DCF: project FCF, discount back, add terminal value."""
    if free_cash_flow <= 0 or shares_outstanding <= 0:
        return ValuationEstimate(
            model_name="DCF", cheap_price=0, fair_price=0, expensive_price=0,
            confidence=0.0, details={},
        )

    if discount_rate <= terminal_growth:
        return ValuationEstimate(
            model_name="DCF", cheap_price=0, fair_price=0, expensive_price=0,
            confidence=0.0, details={},
        )

    # Project FCF
    projected_fcf: list[float] = []
    fcf = free_cash_flow
    for _ in range(projection_years):
        fcf *= (1 + growth_rate)
        projected_fcf.append(fcf)

    # Discount projected FCF
    pv_fcf = sum(
        fcf_i / (1 + discount_rate) ** (i + 1)
        for i, fcf_i in enumerate(projected_fcf)
    )

    # Terminal value
    terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** projection_years

    total_value = pv_fcf + pv_terminal
    fair_per_share = total_value / shares_outstanding

    # Cheap/expensive with margin of safety
    cheap = round(fair_per_share * 0.7, 2)
    fair = round(fair_per_share, 2)
    expensive = round(fair_per_share * 1.3, 2)

    confidence = 0.5  # DCF has many assumptions

    return ValuationEstimate(
        model_name="DCF",
        cheap_price=cheap,
        fair_price=fair,
        expensive_price=expensive,
        confidence=confidence,
        details={
            "fcf": free_cash_flow, "growth_rate": growth_rate,
            "terminal_growth": terminal_growth, "discount_rate": discount_rate,
            "pv_fcf": round(pv_fcf, 2), "pv_terminal": round(pv_terminal, 2),
        },
    )
