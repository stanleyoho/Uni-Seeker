from app.modules.indicators.base import IndicatorResult


class VolumeIndicator:
    name = "VOL"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        volumes: list[int] = list(params.get("volumes", []))
        indicator_type = str(params.get("indicator_type", "OBV"))
        period = int(params.get("period", 5))

        if indicator_type == "OBV":
            return self._calculate_obv(closes, volumes)
        return self._calculate_vma(volumes, period)

    def _calculate_obv(
        self, closes: list[float], volumes: list[int]
    ) -> IndicatorResult:
        n = len(closes)
        obv: list[int | None] = [None] * n
        if n == 0 or len(volumes) != n:
            return IndicatorResult(name=self.name, values={"OBV": obv})

        obv[0] = volumes[0]
        for i in range(1, n):
            prev_obv = obv[i - 1] or 0
            if closes[i] > closes[i - 1]:
                obv[i] = prev_obv + volumes[i]
            elif closes[i] < closes[i - 1]:
                obv[i] = prev_obv - volumes[i]
            else:
                obv[i] = prev_obv
        return IndicatorResult(name=self.name, values={"OBV": obv})

    def _calculate_vma(self, volumes: list[int], period: int) -> IndicatorResult:
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
