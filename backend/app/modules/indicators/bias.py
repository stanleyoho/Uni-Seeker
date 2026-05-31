"""BIAS (price deviation from MA, in %) — TA-Lib backed for the SMA leg.

BIAS = (close - SMA(period)) / SMA(period) * 100

The SMA is now sourced from ``talib.SMA`` via the wrapper; only the
percentage transform remains in pure Python. The MA == 0 guard (which
landed in 2026-05-28 as a defensive against all-zero degenerate
windows) is preserved — TA-Lib happily produces a 0 SMA from an
all-zero window, and the original ZeroDivisionError 500 came from the
``/ ma`` step *after* the MA, not the MA itself.
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import sma as talib_sma


class BiasIndicator:
    name = "BIAS"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        period = int(params.get("period", 20))
        n = len(closes)
        bias: list[float | None] = [None] * n
        if n < period:
            return IndicatorResult(name=self.name, values={"BIAS": bias})

        ma_values = talib_sma(closes, period=period)
        for i in range(n):
            ma = ma_values[i]
            # ma is None for warmup window; ma == 0 guards against
            # degenerate (all-zero) input that would otherwise raise
            # ZeroDivisionError. See indicator-history docstring.
            if ma is None or ma == 0:
                continue
            bias[i] = round((closes[i] - ma) / ma * 100, 4)
        return IndicatorResult(name=self.name, values={"BIAS": bias})
