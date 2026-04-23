from app.modules.indicators.base import IndicatorResult


class PatternIndicator:
    """Detects technical patterns: MA alignment, crossovers, divergence."""
    name = "PATTERN"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        pattern_type = str(params.get("pattern_type", "ma_alignment"))

        if pattern_type == "ma_alignment":
            return self._ma_alignment(closes, params)
        elif pattern_type == "ma_crossover":
            return self._ma_crossover(closes, params)
        elif pattern_type == "kd_signal":
            return self._kd_signal(closes, params)
        elif pattern_type == "rsi_divergence":
            return self._rsi_divergence(closes, params)
        elif pattern_type == "macd_signal":
            return self._macd_signal(closes, params)
        return IndicatorResult(name=self.name, values={})

    def _sma(self, data: list[float], period: int, idx: int) -> float | None:
        if idx < period - 1:
            return None
        return sum(data[idx - period + 1:idx + 1]) / period

    def _ma_alignment(self, closes: list[float], params: dict) -> IndicatorResult:
        """
        Detect MA alignment pattern (多頭排列 / 空頭排列).
        Returns: 2=strong bullish, 1=bullish, 0=neutral, -1=bearish, -2=strong bearish
        """
        periods = [5, 10, 20, 60]
        n = len(closes)
        alignment: list[int | None] = [None] * n

        min_period = max(periods)
        if n < min_period:
            return IndicatorResult(name=self.name, values={"ma_alignment": alignment})

        for i in range(min_period - 1, n):
            mas = [self._sma(closes, p, i) for p in periods]
            if any(m is None for m in mas):
                continue

            # Check if MAs are in order (bullish: short > long)
            bullish = all(mas[j] > mas[j + 1] for j in range(len(mas) - 1))
            bearish = all(mas[j] < mas[j + 1] for j in range(len(mas) - 1))

            if bullish:
                # Check if price is above all MAs (strong bullish)
                alignment[i] = 2 if closes[i] > mas[0] else 1
            elif bearish:
                alignment[i] = -2 if closes[i] < mas[0] else -1
            else:
                alignment[i] = 0

        return IndicatorResult(name=self.name, values={"ma_alignment": alignment})

    def _ma_crossover(self, closes: list[float], params: dict) -> IndicatorResult:
        """
        Detect MA crossover (黃金交叉 / 死亡交叉).
        Returns: 1=golden cross, -1=death cross, 0=no cross
        """
        short_p = int(params.get("short_period", 5))
        long_p = int(params.get("long_period", 20))
        n = len(closes)
        cross: list[int | None] = [None] * n

        if n < long_p + 1:
            return IndicatorResult(name=self.name, values={"ma_crossover": cross})

        for i in range(long_p, n):
            short_now = self._sma(closes, short_p, i)
            long_now = self._sma(closes, long_p, i)
            short_prev = self._sma(closes, short_p, i - 1)
            long_prev = self._sma(closes, long_p, i - 1)

            if None in (short_now, long_now, short_prev, long_prev):
                cross[i] = 0
                continue

            if short_prev <= long_prev and short_now > long_now:
                cross[i] = 1  # Golden cross
            elif short_prev >= long_prev and short_now < long_now:
                cross[i] = -1  # Death cross
            else:
                cross[i] = 0

        return IndicatorResult(name=self.name, values={"ma_crossover": cross})

    def _kd_signal(self, closes: list[float], params: dict) -> IndicatorResult:
        """
        KD signal: golden/death cross + overbought/oversold.
        Returns: 2=oversold+golden, 1=golden, -1=death, -2=overbought+death, 0=neutral
        """
        from app.modules.indicators.kd import KDIndicator

        highs: list[float] = list(params.get("highs", []))
        lows: list[float] = list(params.get("lows", []))
        n = len(closes)
        signal: list[int | None] = [None] * n

        if len(highs) != n or len(lows) != n:
            return IndicatorResult(name=self.name, values={"kd_signal": signal})

        kd_result = KDIndicator().calculate(closes, highs=highs, lows=lows)
        k_values = kd_result.values["K"]
        d_values = kd_result.values["D"]

        for i in range(1, n):
            k_now = k_values[i]
            d_now = d_values[i]
            k_prev = k_values[i - 1]
            d_prev = d_values[i - 1]

            if None in (k_now, d_now, k_prev, d_prev):
                continue

            golden = k_prev <= d_prev and k_now > d_now
            death = k_prev >= d_prev and k_now < d_now

            if golden and k_now < 20:
                signal[i] = 2  # Oversold golden cross (strong buy)
            elif golden:
                signal[i] = 1
            elif death and k_now > 80:
                signal[i] = -2  # Overbought death cross (strong sell)
            elif death:
                signal[i] = -1
            else:
                signal[i] = 0

        return IndicatorResult(name=self.name, values={"kd_signal": signal})

    def _rsi_divergence(self, closes: list[float], params: dict) -> IndicatorResult:
        """
        RSI divergence detection (背離).
        Bullish divergence: price makes new low but RSI doesn't.
        Bearish divergence: price makes new high but RSI doesn't.
        Returns: 1=bullish divergence, -1=bearish divergence, 0=none
        """
        from app.modules.indicators.rsi import RSIIndicator

        period = int(params.get("period", 14))
        lookback = int(params.get("lookback", 10))
        n = len(closes)
        divergence: list[int | None] = [None] * n

        rsi_result = RSIIndicator().calculate(closes, period=period)
        rsi_values = rsi_result.values["RSI"]

        if n < period + lookback:
            return IndicatorResult(name=self.name, values={"rsi_divergence": divergence})

        for i in range(period + lookback, n):
            rsi_now = rsi_values[i]
            if rsi_now is None:
                continue

            price_window = closes[i - lookback:i]
            rsi_window = [v for v in rsi_values[i - lookback:i] if v is not None]

            if not rsi_window:
                continue

            # Bullish: price new low but RSI higher low
            if closes[i] < min(price_window) and rsi_now > min(rsi_window):
                divergence[i] = 1
            # Bearish: price new high but RSI lower high
            elif closes[i] > max(price_window) and rsi_now < max(rsi_window):
                divergence[i] = -1
            else:
                divergence[i] = 0

        return IndicatorResult(name=self.name, values={"rsi_divergence": divergence})

    def _macd_signal(self, closes: list[float], params: dict) -> IndicatorResult:
        """
        MACD signal detection.
        Returns: 2=histogram turning positive from negative (strong buy),
                 1=histogram positive and growing,
                 -1=histogram negative and falling,
                 -2=histogram turning negative from positive (strong sell),
                 0=neutral
        """
        from app.modules.indicators.macd import MACDIndicator

        result = MACDIndicator().calculate(closes)
        hist = result.values.get("histogram", [])
        n = len(closes)
        signal: list[int | None] = [None] * n

        for i in range(1, n):
            h_now = hist[i] if i < len(hist) else None
            h_prev = hist[i - 1] if i - 1 < len(hist) else None

            if h_now is None or h_prev is None:
                continue

            if h_prev <= 0 and h_now > 0:
                signal[i] = 2  # Histogram flip positive
            elif h_prev >= 0 and h_now < 0:
                signal[i] = -2  # Histogram flip negative
            elif h_now > 0 and h_now > h_prev:
                signal[i] = 1  # Growing positive
            elif h_now < 0 and h_now < h_prev:
                signal[i] = -1  # Growing negative
            else:
                signal[i] = 0

        return IndicatorResult(name=self.name, values={"macd_signal": signal})
