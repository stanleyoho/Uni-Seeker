"""MACD indicator — TA-Lib backed.

MACD = (EMA(fast) - EMA(slow)) with a Signal line = EMA(signal_period)
applied to the MACD series, and Histogram = MACD - Signal.

Pre-2026-06-01 this file shipped a hand-rolled EMA seeded with the SMA
of the first ``period`` points. TA-Lib's ``MACD`` uses the same
seeding (the canonical Wilder/Appel recurrence), so the parity test
``test_macd_parity`` passes within ε on shared fixtures. Defaults
``fast=12, slow=26, signal=9`` are unchanged.
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import macd as talib_macd


class MACDIndicator:
    name = "MACD"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal_period = int(params.get("signal", 9))
        macd_line, signal_line, histogram = talib_macd(
            closes, fast=fast, slow=slow, signal=signal_period
        )
        return IndicatorResult(
            name=self.name,
            values={"MACD": macd_line, "signal": signal_line, "histogram": histogram},
        )
