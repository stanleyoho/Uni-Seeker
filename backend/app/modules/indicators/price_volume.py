from app.modules.indicators.base import IndicatorResult


class PriceVolumeIndicator:
    """Derived price-volume indicators: volume ratio, surge, amplitude, new high/low, multi-period change."""

    name = "PV"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        indicator_type = str(params.get("indicator_type", "volume_ratio"))

        if indicator_type == "volume_ratio":
            return self._volume_ratio(closes, params)
        elif indicator_type == "volume_surge":
            return self._volume_surge(closes, params)
        elif indicator_type == "amplitude":
            return self._amplitude(closes, params)
        elif indicator_type == "new_high_low":
            return self._new_high_low(closes, params)
        elif indicator_type == "price_change":
            return self._multi_period_change(closes, params)
        return IndicatorResult(name=self.name, values={})

    def _volume_ratio(self, closes: list[float], params: dict) -> IndicatorResult:
        """Today's volume / N-day average volume."""
        volumes: list[int] = list(params.get("volumes", []))
        period = int(params.get("period", 5))
        n = len(volumes)
        ratio: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"volume_ratio": ratio})

        for i in range(period, n):
            avg = sum(volumes[i - period:i]) / period
            ratio[i] = round(volumes[i] / avg, 4) if avg > 0 else None

        return IndicatorResult(name=self.name, values={"volume_ratio": ratio})

    def _volume_surge(self, closes: list[float], params: dict) -> IndicatorResult:
        """Detect volume surges: volume > N * average volume."""
        volumes: list[int] = list(params.get("volumes", []))
        period = int(params.get("period", 20))
        threshold = float(params.get("threshold", 2.0))
        n = len(volumes)
        surge: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"volume_surge": surge})

        for i in range(period, n):
            avg = sum(volumes[i - period:i]) / period
            if avg > 0:
                multiple = volumes[i] / avg
                surge[i] = round(multiple, 4)

        return IndicatorResult(name=self.name, values={"volume_surge": surge})

    def _amplitude(self, closes: list[float], params: dict) -> IndicatorResult:
        """Daily amplitude: (high - low) / previous close * 100."""
        highs: list[float] = list(params.get("highs", []))
        lows: list[float] = list(params.get("lows", []))
        n = len(closes)
        amp: list[float | None] = [None] * n

        if len(highs) != n or len(lows) != n:
            return IndicatorResult(name=self.name, values={"amplitude": amp})

        for i in range(1, n):
            if closes[i - 1] > 0:
                amp[i] = round((highs[i] - lows[i]) / closes[i - 1] * 100, 4)

        return IndicatorResult(name=self.name, values={"amplitude": amp})

    def _new_high_low(self, closes: list[float], params: dict) -> IndicatorResult:
        """Detect N-day new high or low. Returns 1 (new high), -1 (new low), 0 (neither)."""
        period = int(params.get("period", 20))
        n = len(closes)
        signal: list[int | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"new_high_low": signal})

        for i in range(period, n):
            window = closes[i - period:i]
            if closes[i] > max(window):
                signal[i] = 1
            elif closes[i] < min(window):
                signal[i] = -1
            else:
                signal[i] = 0

        return IndicatorResult(name=self.name, values={"new_high_low": signal})

    def _multi_period_change(self, closes: list[float], params: dict) -> IndicatorResult:
        """Price change % over multiple periods (5, 20, 60, 120, 240 days)."""
        periods = [5, 20, 60, 120, 240]
        n = len(closes)
        results: dict[str, list[float | None]] = {}

        for p in periods:
            change: list[float | None] = [None] * n
            for i in range(p, n):
                if closes[i - p] > 0:
                    change[i] = round(
                        (closes[i] - closes[i - p]) / closes[i - p] * 100, 4
                    )
            results[f"change_{p}d"] = change

        return IndicatorResult(name=self.name, values=results)
