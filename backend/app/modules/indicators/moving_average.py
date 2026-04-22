from app.modules.indicators.base import IndicatorResult


class MovingAverageIndicator:
    name = "MA"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 20))
        ma_type = str(params.get("ma_type", "SMA"))
        n = len(closes)
        ma: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"MA": ma})

        if ma_type == "EMA":
            sma = sum(closes[:period]) / period
            ma[period - 1] = round(sma, 4)
            multiplier = 2.0 / (period + 1)
            for i in range(period, n):
                prev = ma[i - 1]
                if prev is not None:
                    ma[i] = round((closes[i] - prev) * multiplier + prev, 4)
        else:
            window_sum = sum(closes[:period])
            ma[period - 1] = round(window_sum / period, 4)
            for i in range(period, n):
                window_sum += closes[i] - closes[i - period]
                ma[i] = round(window_sum / period, 4)

        return IndicatorResult(name=self.name, values={"MA": ma})
