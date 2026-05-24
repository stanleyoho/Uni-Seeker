"""Stock signals module — smart-money divergence detection and edge generation.

Public API:
    StockSharpDetector — institutional (foreign futures) vs retail (margin
        balance) divergence detector.
    StockSharpSignal   — raw signal dataclass (per-side directions + flag).
    EdgeSignal         — synthesized trading edge dataclass (direction +
        confidence + Chinese reason).
"""
from app.modules.stock_signals.sharp_detector import (
    EdgeSignal,
    StockSharpDetector,
    StockSharpSignal,
)

__all__ = [
    "EdgeSignal",
    "StockSharpDetector",
    "StockSharpSignal",
]
