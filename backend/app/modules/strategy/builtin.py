import math

from app.modules.strategy.base import Signal, StrategyConfig


class MACrossoverStrategy:
    """Buy when short MA crosses above long MA, sell when crosses below."""

    def __init__(self, short_period: int = 5, long_period: int = 20) -> None:
        self.config = StrategyConfig(
            name="MA Crossover",
            description=f"MA({short_period}) crosses MA({long_period})",
            params={"short_period": short_period, "long_period": long_period},
        )
        self._short = short_period
        self._long = long_period

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) < self._long + 1:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        def sma(data: list[float], period: int) -> float:
            return sum(data[-period:]) / period

        short_now = sma(closes, self._short)
        long_now = sma(closes, self._long)
        short_prev = sma(closes[:-1], self._short)
        long_prev = sma(closes[:-1], self._long)

        if short_prev <= long_prev and short_now > long_now:
            return Signal(action="BUY", symbol="", reason=f"MA({self._short}) crossed above MA({self._long})", strength=0.8)
        elif short_prev >= long_prev and short_now < long_now:
            return Signal(action="SELL", symbol="", reason=f"MA({self._short}) crossed below MA({self._long})", strength=0.8)
        return Signal(action="HOLD", symbol="", reason="No crossover")


class RSIOversoldStrategy:
    """Buy when RSI drops below threshold, sell when RSI rises above sell threshold."""

    def __init__(self, period: int = 14, buy_threshold: float = 30.0, sell_threshold: float = 70.0) -> None:
        self.config = StrategyConfig(
            name="RSI Oversold",
            description=f"RSI({period}) buy<{buy_threshold} sell>{sell_threshold}",
            params={"period": period, "buy_threshold": buy_threshold, "sell_threshold": sell_threshold},
        )
        self._period = period
        self._buy = buy_threshold
        self._sell = sell_threshold

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) <= self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(c, 0) for c in changes[-self._period:]]
        losses = [abs(min(c, 0)) for c in changes[-self._period:]]
        avg_gain = sum(gains) / self._period
        avg_loss = sum(losses) / self._period

        if avg_loss == 0:
            rsi = 100.0
        elif avg_gain == 0:
            rsi = 0.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - 100 / (1 + rs)

        if rsi < self._buy:
            return Signal(action="BUY", symbol="", reason=f"RSI={rsi:.1f} < {self._buy}", strength=min((self._buy - rsi) / self._buy, 1.0))
        elif rsi > self._sell:
            return Signal(action="SELL", symbol="", reason=f"RSI={rsi:.1f} > {self._sell}", strength=min((rsi - self._sell) / (100 - self._sell), 1.0))
        return Signal(action="HOLD", symbol="", reason=f"RSI={rsi:.1f} in range")


class MACDCrossoverStrategy:
    """Buy when MACD line crosses above signal line, sell when crosses below."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.config = StrategyConfig(
            name="MACD Crossover",
            description=f"MACD({fast},{slow},{signal}) crossover",
            params={"fast": fast, "slow": slow, "signal": signal},
        )
        self._fast = fast
        self._slow = slow
        self._signal = signal

    def _ema(self, data: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * len(data)
        if len(data) < period:
            return result
        sma = sum(data[:period]) / period
        result[period - 1] = sma
        multiplier = 2.0 / (period + 1)
        for i in range(period, len(data)):
            prev = result[i - 1]
            if prev is not None:
                result[i] = (data[i] - prev) * multiplier + prev
        return result

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        n = len(closes)
        if n < self._slow + self._signal:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        fast_ema = self._ema(closes, self._fast)
        slow_ema = self._ema(closes, self._slow)

        macd_line: list[float | None] = [None] * n
        for i in range(n):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd_line[i] = fast_ema[i] - slow_ema[i]

        macd_start = self._slow - 1
        macd_data = [v for v in macd_line[macd_start:] if v is not None]
        if len(macd_data) < self._signal + 1:
            return Signal(action="HOLD", symbol="", reason="Insufficient MACD data")

        signal_ema = self._ema(macd_data, self._signal)

        # Get current and previous MACD vs signal
        cur_macd = macd_data[-1]
        prev_macd = macd_data[-2]
        cur_signal = signal_ema[-1]
        prev_signal = signal_ema[-2]

        if cur_signal is None or prev_signal is None:
            return Signal(action="HOLD", symbol="", reason="Signal line not ready")

        if prev_macd <= prev_signal and cur_macd > cur_signal:
            return Signal(action="BUY", symbol="", reason=f"MACD crossed above signal ({cur_macd:.2f} > {cur_signal:.2f})", strength=0.8)
        elif prev_macd >= prev_signal and cur_macd < cur_signal:
            return Signal(action="SELL", symbol="", reason=f"MACD crossed below signal ({cur_macd:.2f} < {cur_signal:.2f})", strength=0.8)
        return Signal(action="HOLD", symbol="", reason="No MACD crossover")


class BollingerBounceStrategy:
    """Buy when price touches lower band (mean reversion), sell when touches upper band."""

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.config = StrategyConfig(
            name="Bollinger Bounce",
            description=f"BB({period}, {num_std}σ) bounce",
            params={"period": period, "num_std": num_std},
        )
        self._period = period
        self._num_std = num_std

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        n = len(closes)
        if n < self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        window = closes[-self._period:]
        sma = sum(window) / self._period
        variance = sum((x - sma) ** 2 for x in window) / self._period
        std = math.sqrt(variance)
        upper = sma + self._num_std * std
        lower = sma - self._num_std * std

        price = closes[-1]

        if price <= lower:
            strength = min((lower - price) / (std if std > 0 else 1), 1.0)
            return Signal(action="BUY", symbol="", reason=f"Price {price:.2f} <= lower band {lower:.2f}", strength=abs(strength))
        elif price >= upper:
            strength = min((price - upper) / (std if std > 0 else 1), 1.0)
            return Signal(action="SELL", symbol="", reason=f"Price {price:.2f} >= upper band {upper:.2f}", strength=abs(strength))
        return Signal(action="HOLD", symbol="", reason=f"Price {price:.2f} within bands [{lower:.2f}, {upper:.2f}]")


class BiasReversalStrategy:
    """Buy when negative bias exceeds threshold (oversold), sell when positive bias exceeds threshold."""

    def __init__(self, period: int = 20, buy_threshold: float = -5.0, sell_threshold: float = 5.0) -> None:
        self.config = StrategyConfig(
            name="Bias Reversal",
            description=f"BIAS({period}) buy<{buy_threshold}% sell>{sell_threshold}%",
            params={"period": period, "buy_threshold": buy_threshold, "sell_threshold": sell_threshold},
        )
        self._period = period
        self._buy = buy_threshold
        self._sell = sell_threshold

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        n = len(closes)
        if n < self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        ma = sum(closes[-self._period:]) / self._period
        bias = (closes[-1] - ma) / ma * 100

        if bias <= self._buy:
            strength = min(abs(bias / self._buy), 1.0)
            return Signal(action="BUY", symbol="", reason=f"BIAS={bias:.2f}% <= {self._buy}%", strength=strength)
        elif bias >= self._sell:
            strength = min(bias / self._sell, 1.0)
            return Signal(action="SELL", symbol="", reason=f"BIAS={bias:.2f}% >= {self._sell}%", strength=strength)
        return Signal(action="HOLD", symbol="", reason=f"BIAS={bias:.2f}% in range")


class RSIBiasComboStrategy:
    """Buy when RSI oversold AND negative bias both confirm. Double confirmation for higher accuracy."""

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_buy: float = 30.0,
        rsi_sell: float = 70.0,
        bias_period: int = 20,
        bias_buy: float = -5.0,
        bias_sell: float = 5.0,
    ) -> None:
        self.config = StrategyConfig(
            name="RSI+Bias Combo",
            description=f"RSI({rsi_period})+BIAS({bias_period}) double confirm",
            params={
                "rsi_period": rsi_period, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell,
                "bias_period": bias_period, "bias_buy": bias_buy, "bias_sell": bias_sell,
            },
        )
        self._rsi_period = rsi_period
        self._rsi_buy = rsi_buy
        self._rsi_sell = rsi_sell
        self._bias_period = bias_period
        self._bias_buy = bias_buy
        self._bias_sell = bias_sell

    def _calc_rsi(self, closes: list[float]) -> float | None:
        if len(closes) <= self._rsi_period:
            return None
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(c, 0) for c in changes[-self._rsi_period:]]
        losses = [abs(min(c, 0)) for c in changes[-self._rsi_period:]]
        avg_gain = sum(gains) / self._rsi_period
        avg_loss = sum(losses) / self._rsi_period
        if avg_loss == 0:
            return 100.0
        if avg_gain == 0:
            return 0.0
        return 100 - 100 / (1 + avg_gain / avg_loss)

    def _calc_bias(self, closes: list[float]) -> float | None:
        if len(closes) < self._bias_period:
            return None
        ma = sum(closes[-self._bias_period:]) / self._bias_period
        return (closes[-1] - ma) / ma * 100

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        rsi = self._calc_rsi(closes)
        bias = self._calc_bias(closes)

        if rsi is None or bias is None:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        rsi_buy = rsi < self._rsi_buy
        rsi_sell = rsi > self._rsi_sell
        bias_buy = bias <= self._bias_buy
        bias_sell = bias >= self._bias_sell

        if rsi_buy and bias_buy:
            strength = min((self._rsi_buy - rsi) / self._rsi_buy + abs(bias / self._bias_buy), 2.0) / 2
            return Signal(action="BUY", symbol="", reason=f"RSI={rsi:.1f} + BIAS={bias:.2f}% both oversold", strength=strength)
        elif rsi_sell and bias_sell:
            strength = min((rsi - self._rsi_sell) / (100 - self._rsi_sell) + bias / self._bias_sell, 2.0) / 2
            return Signal(action="SELL", symbol="", reason=f"RSI={rsi:.1f} + BIAS={bias:.2f}% both overbought", strength=strength)
        return Signal(action="HOLD", symbol="", reason=f"RSI={rsi:.1f}, BIAS={bias:.2f}% no double confirm")
