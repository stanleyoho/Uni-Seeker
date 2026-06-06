"""Volume indicators: OBV (On Balance Volume, TA-Lib backed) + VMA
(volume moving average, pure-Python because TA-Lib's MA functions take
float series and volumes are ints; round-tripping through numpy would
add a dependency for no gain).

OBV definition (Granville 1963):
    OBV[0] = volume[0]
    OBV[i] = OBV[i-1] + volume[i] if close[i] > close[i-1]
           = OBV[i-1] - volume[i] if close[i] < close[i-1]
           = OBV[i-1]             otherwise

TA-Lib's ``OBV`` follows the same recurrence; parity verified by
``test_obv_parity``.
"""

from typing import Any

import numpy as np
import talib

from app.modules.indicators.base import IndicatorResult


class VolumeIndicator:
    name = "VOL"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        volumes: list[int] = list(params.get("volumes", []))
        indicator_type = str(params.get("indicator_type", "OBV"))
        period = int(params.get("period", 5))

        if indicator_type == "OBV":
            return self._calculate_obv(closes, volumes)
        return self._calculate_vma(volumes, period)

    def _calculate_obv(self, closes: list[float], volumes: list[int]) -> IndicatorResult:
        n = len(closes)
        obv: list[int | None] = [None] * n
        if n == 0 or len(volumes) != n:
            return IndicatorResult(name=self.name, values={"OBV": obv})

        # TA-Lib OBV returns a float64 array (it operates on float
        # volumes internally). Cast back to int so the return contract
        # — int OBV — matches the hand-rolled implementation.
        obv_arr = talib.OBV(
            np.asarray(closes, dtype=np.float64),
            np.asarray(volumes, dtype=np.float64),
        )
        obv_int: list[int | None] = [int(v) for v in obv_arr.tolist()]
        return IndicatorResult(name=self.name, values={"OBV": obv_int})

    def _calculate_vma(self, volumes: list[int], period: int) -> IndicatorResult:
        # Volumes are ints — keep pure Python to avoid float precision
        # loss. The hand-rolled rolling-sum is O(n) and trivially correct.
        n = len(volumes)
        vma: list[float | None] = [None] * n
        if n < period:
            return IndicatorResult(name=self.name, values={"VMA": vma})

        window_sum = sum(volumes[:period])
        vma[period - 1] = window_sum / period
        for i in range(period, n):
            window_sum += volumes[i] - volumes[i - period]
            vma[i] = window_sum / period
        return IndicatorResult(name=self.name, values={"VMA": vma})
