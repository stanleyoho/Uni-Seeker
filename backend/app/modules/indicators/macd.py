from app.modules.indicators.base import IndicatorResult


def _ema(data: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(data)
    if len(data) < period:
        return result
    sma = sum(data[:period]) / period
    result[period - 1] = sma
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(data)):
        prev = result[i - 1]
        if prev is not None:
            result[i] = round((data[i] - prev) * multiplier + prev, 4)
    return result


class MACDIndicator:
    name = "MACD"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal_period = int(params.get("signal", 9))
        n = len(closes)

        macd_line: list[float | None] = [None] * n
        signal_line: list[float | None] = [None] * n
        histogram: list[float | None] = [None] * n

        if n < slow:
            return IndicatorResult(
                name=self.name,
                values={"MACD": macd_line, "signal": signal_line, "histogram": histogram},
            )

        fast_ema = _ema(closes, fast)
        slow_ema = _ema(closes, slow)

        for i in range(n):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd_line[i] = round(fast_ema[i] - slow_ema[i], 4)

        macd_start = slow - 1
        macd_data = [v for v in macd_line[macd_start:] if v is not None]
        if len(macd_data) >= signal_period:
            signal_ema = _ema(macd_data, signal_period)
            for i, val in enumerate(signal_ema):
                idx = macd_start + i
                if idx < n:
                    signal_line[idx] = val
                    if val is not None and macd_line[idx] is not None:
                        histogram[idx] = round(macd_line[idx] - val, 4)

        return IndicatorResult(
            name=self.name,
            values={"MACD": macd_line, "signal": signal_line, "histogram": histogram},
        )
