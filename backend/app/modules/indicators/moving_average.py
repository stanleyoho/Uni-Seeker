"""Moving Average (SMA/EMA) — TA-Lib backed.

Defaults: ``period=20, ma_type="SMA"``. ``ma_type="EMA"`` switches to
TA-Lib's ``EMA`` which uses the same SMA-seeded recurrence as the old
hand-rolled implementation (verified by ``test_sma_parity`` /
``test_ema_parity``).
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import ema as talib_ema
from app.modules.indicators.talib_wrappers import sma as talib_sma


class MovingAverageIndicator:
    name = "MA"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        period = int(params.get("period", 20))
        ma_type = str(params.get("ma_type", "SMA"))
        if ma_type == "EMA":
            ma = talib_ema(closes, period=period)
        else:
            ma = talib_sma(closes, period=period)
        return IndicatorResult(name=self.name, values={"MA": ma})
