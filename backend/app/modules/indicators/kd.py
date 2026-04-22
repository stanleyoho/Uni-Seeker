from app.modules.indicators.base import IndicatorResult


class KDIndicator:
    name = "KD"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        highs: list[float] = list(params.get("highs", []))
        lows: list[float] = list(params.get("lows", []))
        k_period = int(params.get("k_period", 9))
        k_smooth = int(params.get("k_smooth", 3))
        d_smooth = int(params.get("d_smooth", 3))

        n = len(closes)
        k_values: list[float | None] = [None] * n
        d_values: list[float | None] = [None] * n

        if n < k_period or len(highs) != n or len(lows) != n:
            return IndicatorResult(name=self.name, values={"K": k_values, "D": d_values})

        raw_k: list[float | None] = [None] * n
        for i in range(k_period - 1, n):
            window_high = max(highs[i - k_period + 1 : i + 1])
            window_low = min(lows[i - k_period + 1 : i + 1])
            if window_high == window_low:
                raw_k[i] = 50.0
            else:
                raw_k[i] = round(
                    (closes[i] - window_low) / (window_high - window_low) * 100, 4
                )

        valid_raw = [(i, v) for i, v in enumerate(raw_k) if v is not None]
        for j in range(k_smooth - 1, len(valid_raw)):
            idx = valid_raw[j][0]
            window = [valid_raw[j - k + 1][1] for k in range(k_smooth, 0, -1)]
            k_values[idx] = round(sum(window) / k_smooth, 4)

        valid_k = [(i, v) for i, v in enumerate(k_values) if v is not None]
        for j in range(d_smooth - 1, len(valid_k)):
            idx = valid_k[j][0]
            window = [valid_k[j - k + 1][1] for k in range(d_smooth, 0, -1)]
            d_values[idx] = round(sum(window) / d_smooth, 4)

        return IndicatorResult(name=self.name, values={"K": k_values, "D": d_values})
