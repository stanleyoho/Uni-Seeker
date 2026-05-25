from typing import Any

from app.modules.indicators.base import IndicatorResult


class BiasIndicator:
    name = "BIAS"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        period = int(params.get("period", 20))
        n = len(closes)
        bias: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"BIAS": bias})

        window_sum = sum(closes[:period])
        ma = window_sum / period
        bias[period - 1] = round((closes[period - 1] - ma) / ma * 100, 4)

        for i in range(period, n):
            window_sum += closes[i] - closes[i - period]
            ma = window_sum / period
            bias[i] = round((closes[i] - ma) / ma * 100, 4)

        return IndicatorResult(name=self.name, values={"BIAS": bias})
