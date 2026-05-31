"""Bollinger Bands — TA-Lib backed.

Bands = SMA ± num_std * stdev. Pre-2026-06-01 the math was hand-rolled
using ``math.sqrt`` and a per-window list comprehension; this file now
delegates to ``talib.BBANDS`` via ``talib_wrappers.bbands``. Both
implementations use **population** standard deviation (variance
divided by ``period``, not ``period - 1``) so the parity test
``test_bollinger_parity`` matches within ε.
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import bbands as talib_bbands


class BollingerBandsIndicator:
    name = "BB"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))
        upper, middle, lower = talib_bbands(closes, period=period, num_std=num_std)
        return IndicatorResult(
            name=self.name,
            values={"upper": upper, "middle": middle, "lower": lower},
        )
