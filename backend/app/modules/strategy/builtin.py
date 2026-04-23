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

        # Calculate RSI
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
