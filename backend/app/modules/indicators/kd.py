"""KD (Stochastic Oscillator) — TA-Lib backed.

The Taiwan-market convention this codebase follows:
    raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100
    K     = SMA(raw_k, k_smooth)
    D     = SMA(K,     d_smooth)

with defaults ``k_period=9, k_smooth=3, d_smooth=3``.

TA-Lib's ``STOCH`` is parameterized identically: ``fastk_period=k_period``
plus ``slowk_period=k_smooth`` and ``slowd_period=d_smooth`` with both
``matype=0`` (SMA). The wrapper in ``talib_wrappers.stoch`` sets all
that up, and ``test_kd_parity`` confirms output equivalence within ε.

NOTE: TA-Lib's STOCH only emits values starting at index
``k_period + k_smooth + d_smooth - 3``, which matches the warmup that
the old hand-rolled implementation imposed (raw_k needed k_period-1
bars, then two more SMA chains of length k_smooth and d_smooth).
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import stoch as talib_stoch


class KDIndicator:
    name = "KD"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        highs: list[float] = list(params.get("highs", []))
        lows: list[float] = list(params.get("lows", []))
        k_period = int(params.get("k_period", 9))
        k_smooth = int(params.get("k_smooth", 3))
        d_smooth = int(params.get("d_smooth", 3))

        k_values, d_values = talib_stoch(
            highs,
            lows,
            closes,
            k_period=k_period,
            k_smooth=k_smooth,
            d_smooth=d_smooth,
        )
        return IndicatorResult(
            name=self.name,
            values={"K": k_values, "D": d_values},
        )
