"""Watchlist domain module — pure indicator computation for the live panel.

Compute-only (no I/O). The HTTP layer feeds in daily-close history + a live
price and gets back a ready-to-serialise snapshot. All indicator math is
delegated to ``app.modules.indicators.talib_wrappers`` so there is exactly
one implementation of RSI / SMA in the codebase.
"""

from app.modules.watchlist.live_indicators import (
    LiveIndicatorSnapshot,
    compute_live_indicators,
)

__all__ = ["LiveIndicatorSnapshot", "compute_live_indicators"]
