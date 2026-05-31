"""Built-in trading strategies — TA-Lib backed.

Pre-2026-06-01 every strategy in this file hand-rolled its own SMA / RSI /
MACD / Bollinger / BIAS math. They now delegate to the TA-Lib adapters
in ``app.modules.indicators.talib_wrappers`` so the math is canonical
and shared with ``app.modules.indicators.*``.

Public surface preserved:
    * Class names: MACrossoverStrategy, RSIOversoldStrategy,
      MACDCrossoverStrategy, BollingerBounceStrategy, BiasReversalStrategy,
      RSIBiasComboStrategy.
    * Constructor params + defaults: unchanged.
    * ``evaluate(closes, **kwargs) -> Signal``: signature + Signal shape
      identical to the old version. Strength values may differ at the
      sub-ε level because TA-Lib uses Wilder smoothing seeded on the
      first full window — the old MACrossoverStrategy used a trailing-
      window SMA, so for MA crossovers the numbers match exactly.

Tests:
    * ``tests/unit/modules/test_strategy_base.py`` and the existing
      strategy tests still run unmodified.
    * Indicator-level parity is locked down in
      ``tests/unit/modules/test_talib_parity.py``.
"""

from app.modules.indicators.talib_wrappers import (
    bbands as talib_bbands,
)
from app.modules.indicators.talib_wrappers import (
    macd as talib_macd_full,
)
from app.modules.indicators.talib_wrappers import (
    rsi as talib_rsi,
)
from app.modules.indicators.talib_wrappers import (
    sma as talib_sma,
)
from app.modules.strategy.base import Signal, StrategyConfig


class MACrossoverStrategy:
    """Buy when short MA crosses above long MA, sell when it crosses below.

    Implementation note: TA-Lib's SMA gives the same values as the
    trailing-window sum the original code used, so we can compute both
    SMA series once for the full price history and inspect the last two
    values to detect a cross.
    """

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

        short_series = talib_sma(closes, period=self._short)
        long_series = talib_sma(closes, period=self._long)
        short_now, short_prev = short_series[-1], short_series[-2]
        long_now, long_prev = long_series[-1], long_series[-2]
        if short_now is None or short_prev is None or long_now is None or long_prev is None:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        if short_prev <= long_prev and short_now > long_now:
            return Signal(
                action="BUY",
                symbol="",
                reason=f"MA({self._short}) crossed above MA({self._long})",
                strength=0.8,
            )
        elif short_prev >= long_prev and short_now < long_now:
            return Signal(
                action="SELL",
                symbol="",
                reason=f"MA({self._short}) crossed below MA({self._long})",
                strength=0.8,
            )
        return Signal(action="HOLD", symbol="", reason="No crossover")


class RSIOversoldStrategy:
    """Buy when RSI drops below ``buy_threshold``, sell when it rises above ``sell_threshold``."""

    def __init__(
        self,
        period: int = 14,
        buy_threshold: float = 30.0,
        sell_threshold: float = 70.0,
    ) -> None:
        self.config = StrategyConfig(
            name="RSI Oversold",
            description=f"RSI({period}) buy<{buy_threshold} sell>{sell_threshold}",
            params={
                "period": period,
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
            },
        )
        self._period = period
        self._buy = buy_threshold
        self._sell = sell_threshold

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) <= self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        rsi_series = talib_rsi(closes, period=self._period)
        rsi = rsi_series[-1]
        if rsi is None:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        if rsi < self._buy:
            return Signal(
                action="BUY",
                symbol="",
                reason=f"RSI={rsi:.1f} < {self._buy}",
                strength=min((self._buy - rsi) / self._buy, 1.0),
            )
        elif rsi > self._sell:
            return Signal(
                action="SELL",
                symbol="",
                reason=f"RSI={rsi:.1f} > {self._sell}",
                strength=min((rsi - self._sell) / (100 - self._sell), 1.0),
            )
        return Signal(action="HOLD", symbol="", reason=f"RSI={rsi:.1f} in range")


class MACDCrossoverStrategy:
    """Buy when MACD line crosses above signal line, sell when it crosses below."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.config = StrategyConfig(
            name="MACD Crossover",
            description=f"MACD({fast},{slow},{signal}) crossover",
            params={"fast": fast, "slow": slow, "signal": signal},
        )
        self._fast = fast
        self._slow = slow
        self._signal = signal

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) < self._slow + self._signal:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        macd_line, signal_line, _hist = talib_macd_full(
            closes, fast=self._fast, slow=self._slow, signal=self._signal
        )
        cur_macd, prev_macd = macd_line[-1], macd_line[-2]
        cur_signal, prev_signal = signal_line[-1], signal_line[-2]

        if cur_macd is None or prev_macd is None or cur_signal is None or prev_signal is None:
            return Signal(action="HOLD", symbol="", reason="Signal line not ready")

        if prev_macd <= prev_signal and cur_macd > cur_signal:
            return Signal(
                action="BUY",
                symbol="",
                reason=f"MACD crossed above signal ({cur_macd:.2f} > {cur_signal:.2f})",
                strength=0.8,
            )
        elif prev_macd >= prev_signal and cur_macd < cur_signal:
            return Signal(
                action="SELL",
                symbol="",
                reason=f"MACD crossed below signal ({cur_macd:.2f} < {cur_signal:.2f})",
                strength=0.8,
            )
        return Signal(action="HOLD", symbol="", reason="No MACD crossover")


class BollingerBounceStrategy:
    """Buy when price touches the lower band (mean reversion), sell on upper-band touch."""

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.config = StrategyConfig(
            name="Bollinger Bounce",
            description=f"BB({period}, {num_std}σ) bounce",
            params={"period": period, "num_std": num_std},
        )
        self._period = period
        self._num_std = num_std

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) < self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        upper_series, middle_series, lower_series = talib_bbands(
            closes, period=self._period, num_std=self._num_std
        )
        upper, middle, lower = upper_series[-1], middle_series[-1], lower_series[-1]
        if upper is None or middle is None or lower is None:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        # Derive the std envelope back out of the bands to compute
        # signal strength as a multiple of σ from the touched band
        # (matches the original strength formula).
        std = (upper - middle) / self._num_std if self._num_std else 0.0
        price = closes[-1]

        if price <= lower:
            strength = min((lower - price) / (std if std > 0 else 1), 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"Price {price:.2f} <= lower band {lower:.2f}",
                strength=abs(strength),
            )
        elif price >= upper:
            strength = min((price - upper) / (std if std > 0 else 1), 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"Price {price:.2f} >= upper band {upper:.2f}",
                strength=abs(strength),
            )
        return Signal(
            action="HOLD",
            symbol="",
            reason=f"Price {price:.2f} within bands [{lower:.2f}, {upper:.2f}]",
        )


class BiasReversalStrategy:
    """Buy when negative bias exceeds threshold (oversold), sell when
    positive bias exceeds threshold."""

    def __init__(
        self,
        period: int = 20,
        buy_threshold: float = -5.0,
        sell_threshold: float = 5.0,
    ) -> None:
        self.config = StrategyConfig(
            name="Bias Reversal",
            description=f"BIAS({period}) buy<{buy_threshold}% sell>{sell_threshold}%",
            params={
                "period": period,
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
            },
        )
        self._period = period
        self._buy = buy_threshold
        self._sell = sell_threshold

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) < self._period:
            return Signal(action="HOLD", symbol="", reason="Insufficient data")

        ma_series = talib_sma(closes, period=self._period)
        ma = ma_series[-1]
        # Guard: degenerate all-zero window → ma == 0 → undefined bias.
        # Preserves the 2026-05-28 ZeroDivisionError fix.
        if ma is None or ma == 0:
            return Signal(action="HOLD", symbol="", reason="Degenerate data (MA=0)")
        bias = (closes[-1] - ma) / ma * 100

        if bias <= self._buy:
            strength = min(abs(bias / self._buy), 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"BIAS={bias:.2f}% <= {self._buy}%",
                strength=strength,
            )
        elif bias >= self._sell:
            strength = min(bias / self._sell, 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"BIAS={bias:.2f}% >= {self._sell}%",
                strength=strength,
            )
        return Signal(action="HOLD", symbol="", reason=f"BIAS={bias:.2f}% in range")


class RSIBiasComboStrategy:
    """Buy when RSI is oversold AND negative BIAS confirms. Double
    confirmation for higher accuracy."""

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
                "rsi_period": rsi_period,
                "rsi_buy": rsi_buy,
                "rsi_sell": rsi_sell,
                "bias_period": bias_period,
                "bias_buy": bias_buy,
                "bias_sell": bias_sell,
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
        return talib_rsi(closes, period=self._rsi_period)[-1]

    def _calc_bias(self, closes: list[float]) -> float | None:
        if len(closes) < self._bias_period:
            return None
        ma_series = talib_sma(closes, period=self._bias_period)
        ma = ma_series[-1]
        # Guard: degenerate (all-zero) window → undefined bias.
        if ma is None or ma == 0:
            return None
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
            strength = (
                min((self._rsi_buy - rsi) / self._rsi_buy + abs(bias / self._bias_buy), 2.0) / 2
            )
            return Signal(
                action="BUY",
                symbol="",
                reason=f"RSI={rsi:.1f} + BIAS={bias:.2f}% both oversold",
                strength=strength,
            )
        elif rsi_sell and bias_sell:
            strength = (
                min((rsi - self._rsi_sell) / (100 - self._rsi_sell) + bias / self._bias_sell, 2.0)
                / 2
            )
            return Signal(
                action="SELL",
                symbol="",
                reason=f"RSI={rsi:.1f} + BIAS={bias:.2f}% both overbought",
                strength=strength,
            )
        return Signal(
            action="HOLD",
            symbol="",
            reason=f"RSI={rsi:.1f}, BIAS={bias:.2f}% no double confirm",
        )
