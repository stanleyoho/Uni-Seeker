from app.modules.indicators.base import IndicatorResult


class RSIIndicator:
    name = "RSI"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 14))
        n = len(closes)
        rsi: list[float | None] = [None] * n

        if n <= period:
            return IndicatorResult(name=self.name, values={"RSI": rsi})

        changes = [closes[i] - closes[i - 1] for i in range(1, n)]
        gains = [max(c, 0.0) for c in changes[:period]]
        losses = [abs(min(c, 0.0)) for c in changes[:period]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi[period] = 100.0
        elif avg_gain == 0:
            rsi[period] = 0.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = round(100 - 100 / (1 + rs), 4)

        for i in range(period + 1, n):
            change = changes[i - 1]
            gain = max(change, 0.0)
            loss = abs(min(change, 0.0))
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            if avg_loss == 0:
                rsi[i] = 100.0
            elif avg_gain == 0:
                rsi[i] = 0.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = round(100 - 100 / (1 + rs), 4)

        return IndicatorResult(name=self.name, values={"RSI": rsi})
