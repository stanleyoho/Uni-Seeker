from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class EstimateResult:
    model_type: str
    cheap_price: Decimal | None
    fair_price: Decimal | None
    expensive_price: Decimal | None
    confidence: Decimal
    details: dict[str, Any] = field(default_factory=dict)


class PriceEstimator(Protocol):
    async def estimate(self, stock_id: int) -> EstimateResult:
        """Calculate price estimate for a given stock."""
        ...
