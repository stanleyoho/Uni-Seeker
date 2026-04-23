from dataclasses import dataclass


@dataclass(frozen=True)
class ValuationEstimate:
    model_name: str
    cheap_price: float  # undervalued
    fair_price: float   # fair value
    expensive_price: float  # overvalued
    confidence: float   # 0.0 - 1.0 (based on data completeness)
    details: dict[str, float]  # model-specific details
