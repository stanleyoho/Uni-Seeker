from app.modules.price_estimator.base import ValuationEstimate


def composite_estimate(estimates: list[ValuationEstimate]) -> ValuationEstimate:
    """Combine multiple valuation estimates using confidence-weighted average."""
    valid = [e for e in estimates if e.confidence > 0 and e.fair_price > 0]
    if not valid:
        return ValuationEstimate(
            model_name="Composite", cheap_price=0, fair_price=0,
            expensive_price=0, confidence=0.0, details={},
        )

    total_weight = sum(e.confidence for e in valid)

    cheap = sum(e.cheap_price * e.confidence for e in valid) / total_weight
    fair = sum(e.fair_price * e.confidence for e in valid) / total_weight
    expensive = sum(e.expensive_price * e.confidence for e in valid) / total_weight

    avg_confidence = total_weight / len(valid)

    return ValuationEstimate(
        model_name="Composite",
        cheap_price=round(cheap, 2),
        fair_price=round(fair, 2),
        expensive_price=round(expensive, 2),
        confidence=round(avg_confidence, 2),
        details={
            "models_used": [e.model_name for e in valid],
            "weights": {e.model_name: round(e.confidence, 2) for e in valid},
        },
    )
