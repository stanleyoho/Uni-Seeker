import math

from app.modules.indicators.base import IndicatorResult


class BollingerBandsIndicator:
    name = "BB"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))
        n = len(closes)

        upper: list[float | None] = [None] * n
        middle: list[float | None] = [None] * n
        lower: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(
                name=self.name,
                values={"upper": upper, "middle": middle, "lower": lower},
            )

        for i in range(period - 1, n):
            window = closes[i - period + 1 : i + 1]
            sma = sum(window) / period
            variance = sum((x - sma) ** 2 for x in window) / period
            std = math.sqrt(variance)
            middle[i] = round(sma, 4)
            upper[i] = round(sma + num_std * std, 4)
            lower[i] = round(sma - num_std * std, 4)

        return IndicatorResult(
            name=self.name,
            values={"upper": upper, "middle": middle, "lower": lower},
        )
