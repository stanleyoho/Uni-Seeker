"""Service layer for the 四大買賣點 (Best Four Buy/Sell Points) feature.

Owns the universe scan + persistence side: read the full TW universe's daily
OHLCV from the DB, run the pure ``app.modules.best_four_point`` calculator
over each symbol, and persist today's per-symbol outcome into the
``signal_scans`` table (reusing ``SignalScanRecord`` — its docstring is
literally "snapshot of scan output for a symbol on a given date").
"""

from app.services.best_four_point.scan_service import (
    SCAN_KIND,
    read_cached_scan,
    run_best_four_point_scan,
)

__all__ = [
    "SCAN_KIND",
    "read_cached_scan",
    "run_best_four_point_scan",
]
