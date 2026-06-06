"""四大買賣點 (Best Four Buy/Sell Points) — faithful reimplementation of
twstock's ``BestFourPoint`` heuristic on Uni-Seeker's own OHLCV data.

Pure computation only — no DB, no I/O. See ``calculator.py`` for the
algorithm and its documented thresholds. The universe-scan + persistence
side lives in ``app.services.best_four_point`` (service layer), and the
HTTP surface in ``app.api.v1.scanner``.
"""

from app.modules.best_four_point.calculator import (
    BestFourPointResult,
    OHLCVSeries,
    compute_best_four_point,
)

__all__ = [
    "BestFourPointResult",
    "OHLCVSeries",
    "compute_best_four_point",
]
