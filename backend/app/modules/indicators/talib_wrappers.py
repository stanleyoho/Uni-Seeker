"""TA-Lib adapters.

A thin layer that takes ``list[float]`` (the format every existing
indicator caller in this project uses) and returns ``list[float | None]``
with TA-Lib's NaN warmup positions converted to ``None`` so they slot
straight into the existing ``IndicatorResult.values`` shape.

Why a separate module:
    * Every per-indicator file in ``app/modules/indicators/`` previously
      hand-rolled the math. Calling ``talib.RSI`` directly from each file
      duplicates the same numpy conversion + NaN-mapping boilerplate. This
      module owns that conversion once.
    * Tests for indicator parity (``tests/unit/modules/test_talib_parity.py``)
      drive these wrappers directly, so any regression — e.g. someone
      accidentally returning ``float('nan')`` instead of ``None`` — fails
      fast at the unit-test level rather than via an opaque downstream
      consumer crash (``TypeError: '<' not supported between NaN`` etc).
    * Keeps ``import talib`` localized to a single module — if TA-Lib's
      build ever breaks on a CI runner, only this file (and tests) need
      to be probed for fallout.

Return-shape contract:
    * Input length ``n`` → output length ``n`` (1:1, just like hand-rolled).
    * Warmup positions (insufficient lookback) → ``None``, matching the
      ``list[float | None]`` placeholder pattern the rest of the codebase
      uses (e.g. ``RSIIndicator.calculate`` returning ``[None] * period``
      followed by computed values).
    * Numeric values are rounded to 4 decimal places to match the
      pre-existing rounding behavior across the indicator suite
      (RSIIndicator, MACDIndicator, BollingerBandsIndicator all round to
      4 places). This keeps existing-test fixtures stable.
"""

from __future__ import annotations

import math

import numpy as np
import talib  # type: ignore[import-not-found]


def _to_list(arr: np.ndarray) -> list[float | None]:
    """Convert a numpy float array to ``list[float | None]``.

    TA-Lib returns ``np.nan`` for the warmup period (positions where the
    indicator hasn't accumulated enough lookback). The rest of this
    project models warmup as Python ``None``. Convert NaN → None and
    round real numbers to 4 decimals to match hand-rolled precision.
    """
    out: list[float | None] = []
    for v in arr.tolist():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(round(float(v), 4))
    return out


def _to_int_list(arr: np.ndarray) -> list[int | None]:
    """Convert a numpy int/float array to ``list[int | None]`` (NaN → None)."""
    out: list[int | None] = []
    for v in arr.tolist():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(int(v))
    return out


def _as_np(closes: list[float]) -> np.ndarray:
    """Coerce a Python list to the float64 numpy array TA-Lib requires."""
    return np.asarray(closes, dtype=np.float64)


# ── Single-series indicators ────────────────────────────────────────────────


def sma(closes: list[float], period: int) -> list[float | None]:
    """Simple Moving Average over ``period`` bars."""
    if len(closes) < period:
        return [None] * len(closes)
    return _to_list(talib.SMA(_as_np(closes), timeperiod=period))


def ema(closes: list[float], period: int) -> list[float | None]:
    """Exponential Moving Average over ``period`` bars."""
    if len(closes) < period:
        return [None] * len(closes)
    return _to_list(talib.EMA(_as_np(closes), timeperiod=period))


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index. Returns ``None`` for the first ``period`` bars.

    TA-Lib uses Wilder's smoothing (the canonical RSI definition Welles
    Wilder published in 1978). Our hand-rolled RSIIndicator also uses
    Wilder's smoothing — see the ``avg_gain = (avg_gain * (period - 1) +
    gain) / period`` recurrence — so values match to within ε on shared
    fixtures (validated in ``tests/unit/modules/test_talib_parity.py``).
    """
    if len(closes) <= period:
        return [None] * len(closes)
    return _to_list(talib.RSI(_as_np(closes), timeperiod=period))


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line / signal line / histogram.

    Returns a tuple ``(macd, signal, hist)`` matching the keys
    ``("MACD", "signal", "histogram")`` that MACDIndicator exposes.
    """
    n = len(closes)
    if n < slow:
        return [None] * n, [None] * n, [None] * n
    macd_arr, signal_arr, hist_arr = talib.MACD(
        _as_np(closes),
        fastperiod=fast,
        slowperiod=slow,
        signalperiod=signal,
    )
    return _to_list(macd_arr), _to_list(signal_arr), _to_list(hist_arr)


def bbands(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands: ``(upper, middle, lower)``.

    TA-Lib's ``BBANDS`` uses the population standard deviation by default
    (``nbdevup=nbdevdn=2.0`` is the multiplier). Our hand-rolled
    BollingerBandsIndicator also uses population std (``variance = sum /
    period``, not ``/ (period - 1)``), so the two implementations agree
    on the same fixtures.
    """
    n = len(closes)
    if n < period:
        return [None] * n, [None] * n, [None] * n
    upper, middle, lower = talib.BBANDS(
        _as_np(closes),
        timeperiod=period,
        nbdevup=num_std,
        nbdevdn=num_std,
        matype=0,  # 0 = SMA, which is what hand-rolled uses
    )
    return _to_list(upper), _to_list(middle), _to_list(lower)


# ── OHLC indicators (need high/low/close, sometimes open) ──────────────────


def stoch(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_period: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """KD (Stochastic Oscillator). Returns ``(K, D)`` value lists.

    NOTE: KDIndicator uses TWSE-style smoothing (the ``raw_k`` -> ``K`` ->
    ``D`` two-step SMA chain). TA-Lib's ``STOCH`` is parameterized to
    match: ``slowk_period=k_smooth``, ``slowd_period=d_smooth``, both SMA
    (``matype=0``). Verified equivalent on fixtures in
    ``tests/unit/modules/test_talib_parity.py``.
    """
    n = len(closes)
    if n < k_period or len(highs) != n or len(lows) != n:
        return [None] * n, [None] * n
    k_arr, d_arr = talib.STOCH(
        _as_np(highs),
        _as_np(lows),
        _as_np(closes),
        fastk_period=k_period,
        slowk_period=k_smooth,
        slowk_matype=0,
        slowd_period=d_smooth,
        slowd_matype=0,
    )
    return _to_list(k_arr), _to_list(d_arr)


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Average True Range — volatility measure. Returns ``None``-padded."""
    n = len(closes)
    if n <= period or len(highs) != n or len(lows) != n:
        return [None] * n
    return _to_list(talib.ATR(_as_np(highs), _as_np(lows), _as_np(closes), timeperiod=period))


# ── Candlestick pattern detection ──────────────────────────────────────────
#
# TA-Lib pattern functions return an int array per bar:
#   +100 = bullish pattern detected at this bar
#   -100 = bearish pattern detected at this bar
#      0 = no pattern
# Some patterns (e.g. CDLENGULFING) emit ±100 depending on direction; others
# (CDLDOJI) only ever emit +100 because they're directionally neutral.
#
# Exposed as a dict so callers can probe "is pattern X firing on the latest
# bar?" with a single dict lookup, and the candlestick patterns endpoint
# can iterate the dict to build the response list.


PATTERN_FUNCS = {
    "CDLDOJI": "CDLDOJI",
    "CDLENGULFING": "CDLENGULFING",
    "CDLHAMMER": "CDLHAMMER",
    "CDLMORNINGSTAR": "CDLMORNINGSTAR",
    "CDLEVENINGSTAR": "CDLEVENINGSTAR",
    "CDLSHOOTINGSTAR": "CDLSHOOTINGSTAR",
}


def pattern(
    name: str,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> list[int | None]:
    """Run a single TA-Lib candlestick pattern function by name.

    ``name`` must be one of the keys in ``PATTERN_FUNCS`` (validated to
    prevent arbitrary getattr on the talib module). Returns the per-bar
    int signal list with NaN warmup positions mapped to ``None``.
    """
    if name not in PATTERN_FUNCS:
        raise ValueError(f"Unknown pattern '{name}'. Available: {sorted(PATTERN_FUNCS)}")
    n = len(closes)
    if n == 0 or len(opens) != n or len(highs) != n or len(lows) != n:
        return [None] * n
    func = getattr(talib, PATTERN_FUNCS[name])
    return _to_int_list(func(_as_np(opens), _as_np(highs), _as_np(lows), _as_np(closes)))
