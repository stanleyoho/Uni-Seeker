"""Alpha158-style factor implementations over a single symbol's OHLCV.

Inspiration & honesty notes
===========================
These factors are modelled on Microsoft Qlib's **Alpha158** handcrafted
feature set (`qlib.contrib.data.handler.Alpha158`). We re-implement a
representative *subset* directly — there is **no** ``qlib`` dependency.

Two structural differences from the Qlib originals, stated up front so the
reader is not misled:

1. **Scalar, not panel.** Qlib's Alpha158 emits a *time series* of each
   feature aligned to a label horizon for cross-sectional ML training. Here
   each factor returns a single ``float`` evaluated on the **latest bar**,
   because the consumer is an on-demand "factor vector for a symbol"
   endpoint, not a training pipeline.
2. **Normalisation.** Qlib normalises many features by the latest close
   (e.g. ``KMID = (close-open)/open`` but several K-features are divided by
   ``close``; ROC is ``Ref(close, d)/close``). We follow Qlib's *relative*
   formulation faithfully where it is unambiguous and note any deviation
   per-factor. Factors marked **"approx"** in their docstring are close in
   spirit but not bit-identical to the Qlib expression.

OHLCV input contract
====================
Every factor takes a :class:`pandas.DataFrame` with lower-case columns
``open``, ``high``, ``low``, ``close``, ``volume``, ordered **oldest bar
first** (so ``df.iloc[-1]`` is the most recent bar). Functions return
``None`` when the frame is too short for the requested lookback, mirroring
the ``None``-warmup convention used across this repo's indicator suite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Columns every factor relies on. Validated once in compute_factor_vector.
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")

# A factor is a pure callable: OHLCV frame -> latest-bar scalar (or None).
FactorFn = Callable[[pd.DataFrame], "float | None"]


def _closes(df: pd.DataFrame) -> np.ndarray:
    """Return the close column as a float64 numpy array."""
    # pandas is in mypy's ignore_missing_imports list, so `.to_numpy` is
    # typed as Any; the explicit np.asarray pins the return to np.ndarray.
    return np.asarray(df["close"].to_numpy(dtype=np.float64), dtype=np.float64)


def _finite(value: float) -> float | None:
    """Map NaN / inf to ``None`` so callers never see non-finite floats."""
    if not np.isfinite(value):
        return None
    return round(float(value), 6)


# ── Candle geometry (Alpha158 "K" features) ────────────────────────────────


def kmid(df: pd.DataFrame) -> float | None:
    """KMID — body of the latest candle relative to its open.

    Formula (Qlib): ``(close - open) / open``.

    Positive when the bar closed above its open (bullish body), negative
    otherwise. Magnitude is the intraday body return. Identical to the Qlib
    ``KMID`` expression.
    """
    if df.empty:
        return None
    last = df.iloc[-1]
    o = float(last["open"])
    if o == 0.0:
        return None
    return _finite((float(last["close"]) - o) / o)


def klen(df: pd.DataFrame) -> float | None:
    """KLEN — total candle range relative to open.

    Formula (Qlib): ``(high - low) / open``.

    The full high-to-low span normalised by the open; a volatility-of-the-bar
    proxy. Identical to the Qlib ``KLEN`` expression.
    """
    if df.empty:
        return None
    last = df.iloc[-1]
    o = float(last["open"])
    if o == 0.0:
        return None
    return _finite((float(last["high"]) - float(last["low"])) / o)


def kup(df: pd.DataFrame) -> float | None:
    """KUP — upper shadow relative to open.

    Formula (Qlib): ``(high - max(open, close)) / open``.

    Length of the wick above the candle body, normalised by open. Large
    values indicate intraday rejection of higher prices. Identical to the
    Qlib ``KUP`` expression.
    """
    if df.empty:
        return None
    last = df.iloc[-1]
    o = float(last["open"])
    if o == 0.0:
        return None
    upper = float(last["high"]) - max(o, float(last["close"]))
    return _finite(upper / o)


def klow(df: pd.DataFrame) -> float | None:
    """KLOW — lower shadow relative to open.

    Formula (Qlib): ``(min(open, close) - low) / open``.

    Length of the wick below the candle body, normalised by open. Large
    values indicate intraday rejection of lower prices (buying support).
    Identical to the Qlib ``KLOW`` expression.
    """
    if df.empty:
        return None
    last = df.iloc[-1]
    o = float(last["open"])
    if o == 0.0:
        return None
    lower = min(o, float(last["close"])) - float(last["low"])
    return _finite(lower / o)


# ── Momentum / rate-of-change ──────────────────────────────────────────────


def roc(df: pd.DataFrame, window: int) -> float | None:
    """ROC — rate of change over ``window`` bars.

    Formula: ``close[t] / close[t-window] - 1``.

    Note vs Qlib: Alpha158's ``ROC{d}`` is ``Ref($close, d) / $close`` (the
    *reciprocal* orientation — past over present). We use the conventional
    ``present/past - 1`` so a positive value means the price *rose*, which is
    the intuitive sign for a momentum factor. Magnitude is the simple return
    over the window. Marked **approx** (sign/offset convention differs from
    the literal Qlib expression).
    """
    closes = _closes(df)
    if window <= 0 or len(closes) <= window:
        return None
    past = closes[-1 - window]
    if past == 0.0:
        return None
    return _finite(closes[-1] / past - 1.0)


def ma_ratio(df: pd.DataFrame, window: int) -> float | None:
    """MA ratio — latest close relative to its ``window``-bar moving average.

    Formula (Qlib ``MA{d}``): ``mean(close, window) / close``.

    Values < 1 mean price is above its average (uptrend / extended);
    values > 1 mean price is below its average. Identical to the Qlib
    ``MA{d}`` expression (MA normalised by the latest close).
    """
    closes = _closes(df)
    if window <= 0 or len(closes) < window:
        return None
    last = closes[-1]
    if last == 0.0:
        return None
    ma = float(np.mean(closes[-window:]))
    return _finite(ma / last)


# ── Volatility ─────────────────────────────────────────────────────────────


def std_factor(df: pd.DataFrame, window: int) -> float | None:
    """STD — volatility: std-dev of close over ``window`` bars, normalised.

    Formula (Qlib ``STD{d}``): ``std(close, window) / close``.

    Uses the population standard deviation (``ddof=0``) to match Qlib's
    rolling ``std`` (pandas ``Rolling.std`` defaults to sample ``ddof=1``,
    but Qlib's C++/expression backend uses population std). Normalised by the
    latest close so the factor is scale-free. Identical in spirit to Qlib's
    ``STD{d}``; we pin ``ddof=0`` explicitly.
    """
    closes = _closes(df)
    if window <= 0 or len(closes) < window:
        return None
    last = closes[-1]
    if last == 0.0:
        return None
    std = float(np.std(closes[-window:], ddof=0))
    return _finite(std / last)


# ── Volume ─────────────────────────────────────────────────────────────────


def volume_ratio(df: pd.DataFrame, window: int) -> float | None:
    """VMA-ratio — latest volume relative to its ``window``-bar average.

    Formula (Qlib ``VMA{d}``): ``mean(volume, window) / volume``.

    A spike day has volume well above its average, so this ratio is < 1; a
    quiet day is > 1. Identical to the Qlib ``VMA{d}`` expression (volume MA
    normalised by latest volume). Returns ``None`` if the latest volume is 0
    (e.g. a halted/suspended bar).
    """
    if df.empty:
        return None
    volumes = df["volume"].to_numpy(dtype=np.float64)
    if window <= 0 or len(volumes) < window:
        return None
    last = volumes[-1]
    if last == 0.0:
        return None
    vma = float(np.mean(volumes[-window:]))
    return _finite(vma / last)


# ── Oscillators ────────────────────────────────────────────────────────────


def rsi_factor(df: pd.DataFrame, window: int = 14) -> float | None:
    """RSI — Wilder's Relative Strength Index on the latest bar (0..100).

    Computed via TA-Lib's ``RSI`` (Wilder smoothing) and returning the most
    recent value. Not part of Alpha158's literal feature list, but RSI is the
    canonical oscillator and a natural member of an Alpha-style price factor
    set. Returns ``None`` until ``window`` bars of lookback exist.
    """
    closes = _closes(df)
    if window <= 0 or len(closes) <= window:
        return None
    # Local import keeps `import talib` localised (mirrors talib_wrappers.py).
    import talib

    values = talib.RSI(closes, timeperiod=window)
    latest = values[-1]
    if latest is None or not np.isfinite(latest):
        return None
    return _finite(float(latest))


def williams_r(df: pd.DataFrame, window: int = 14) -> float | None:
    """Williams %R over ``window`` bars (-100..0).

    Formula: ``-100 * (highest_high - close) / (highest_high - lowest_low)``
    over the trailing ``window`` bars (using each bar's high/low). Near 0 =
    close sits at the top of its recent range (overbought); near -100 =
    bottom of range (oversold). The momentum-position cousin of Stochastic
    %K. Returns ``None`` if the range is degenerate (flat window).
    """
    if window <= 0 or len(df) < window:
        return None
    window_df = df.iloc[-window:]
    highest = float(window_df["high"].max())
    lowest = float(window_df["low"].min())
    close = float(df.iloc[-1]["close"])
    rng = highest - lowest
    if rng == 0.0:
        return None
    return _finite(-100.0 * (highest - close) / rng)


# ── Range position (Alpha158 IMAX / IMIN family) ───────────────────────────


def max_position(df: pd.DataFrame, window: int) -> float | None:
    """IMAX — where the highest close sits within the trailing window.

    Formula (Qlib ``IMAX{d}``): ``argmax(high, window) / window``.

    0.0 means the window's peak is the *oldest* bar, ~1.0 means the peak is
    the *most recent* bar. Uses the ``high`` series, like Qlib's ``IMAX``.
    A recency-of-peak signal. Identical to the Qlib ``IMAX{d}`` expression.
    """
    if window <= 0 or len(df) < window:
        return None
    highs = df["high"].to_numpy(dtype=np.float64)[-window:]
    idx = int(np.argmax(highs))
    return _finite(idx / window)


def min_position(df: pd.DataFrame, window: int) -> float | None:
    """IMIN — where the lowest low sits within the trailing window.

    Formula (Qlib ``IMIN{d}``): ``argmin(low, window) / window``.

    0.0 means the window's trough is the *oldest* bar, ~1.0 means the trough
    is the *most recent* bar. Uses the ``low`` series, like Qlib's ``IMIN``.
    Identical to the Qlib ``IMIN{d}`` expression.
    """
    if window <= 0 or len(df) < window:
        return None
    lows = df["low"].to_numpy(dtype=np.float64)[-window:]
    idx = int(np.argmin(lows))
    return _finite(idx / window)


# ── Cross-asset: beta to a reference index ─────────────────────────────────


def beta_to_index(
    df: pd.DataFrame,
    index_df: pd.DataFrame,
    window: int = 60,
) -> float | None:
    """BETA — OLS beta of the symbol's returns vs a reference index.

    Formula: ``cov(r_sym, r_idx) / var(r_idx)`` over the trailing ``window``
    daily returns, where ``r = close.pct_change()``. This is the classic CAPM
    beta. Qlib's Alpha158 does not include a market-beta feature (it is a
    single-series handler); beta is added here because it is a staple of any
    serious quant factor set and the repo already has an index price series
    available. Marked **extension** (beyond literal Alpha158).

    Both frames are aligned to their last ``window + 1`` overlapping bars by
    position (callers pass already-date-aligned series). Returns ``None`` if
    either series is too short or the index has zero return variance.
    """
    if window <= 0:
        return None
    sym_close = _closes(df)
    idx_close = index_df["close"].to_numpy(dtype=np.float64)
    n = window + 1
    if len(sym_close) < n or len(idx_close) < n:
        return None
    sym_ret = np.diff(sym_close[-n:]) / sym_close[-n:-1]
    idx_ret = np.diff(idx_close[-n:]) / idx_close[-n:-1]
    if not (np.all(np.isfinite(sym_ret)) and np.all(np.isfinite(idx_ret))):
        return None
    var_idx = float(np.var(idx_ret, ddof=0))
    if var_idx == 0.0:
        return None
    cov = float(np.cov(sym_ret, idx_ret, ddof=0)[0, 1])
    return _finite(cov / var_idx)


# ── Registry ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FactorSpec:
    """A named, documented factor with a bound parameterisation.

    ``fn`` is the pure factor callable already closed over its window args
    (so the registry can be evaluated uniformly without per-factor argument
    plumbing). ``formula`` is the human-readable expression surfaced via the
    API and used as living documentation.
    """

    name: str
    formula: str
    fn: FactorFn


def _spec(name: str, formula: str, fn: FactorFn) -> FactorSpec:
    return FactorSpec(name=name, formula=formula, fn=fn)


# The bounded v1 factor set. Windows chosen to mirror Alpha158's common
# horizons (5 / 10 / 20 / 60 day) without exploding the surface area.
FACTORS: dict[str, FactorSpec] = {
    "KMID": _spec("KMID", "(close - open) / open", kmid),
    "KLEN": _spec("KLEN", "(high - low) / open", klen),
    "KUP": _spec("KUP", "(high - max(open, close)) / open", kup),
    "KLOW": _spec("KLOW", "(min(open, close) - low) / open", klow),
    "ROC5": _spec("ROC5", "close[t] / close[t-5] - 1", lambda d: roc(d, 5)),
    "ROC20": _spec("ROC20", "close[t] / close[t-20] - 1", lambda d: roc(d, 20)),
    "ROC60": _spec("ROC60", "close[t] / close[t-60] - 1", lambda d: roc(d, 60)),
    "MA5": _spec("MA5", "mean(close, 5) / close", lambda d: ma_ratio(d, 5)),
    "MA20": _spec("MA20", "mean(close, 20) / close", lambda d: ma_ratio(d, 20)),
    "STD20": _spec("STD20", "std(close, 20) / close", lambda d: std_factor(d, 20)),
    "VMA5": _spec("VMA5", "mean(volume, 5) / volume", lambda d: volume_ratio(d, 5)),
    "RSI14": _spec("RSI14", "Wilder RSI(close, 14)", lambda d: rsi_factor(d, 14)),
    "WILLR14": _spec(
        "WILLR14",
        "-100 * (max(high,14) - close) / (max(high,14) - min(low,14))",
        lambda d: williams_r(d, 14),
    ),
    "IMAX20": _spec("IMAX20", "argmax(high, 20) / 20", lambda d: max_position(d, 20)),
    "IMIN20": _spec("IMIN20", "argmin(low, 20) / 20", lambda d: min_position(d, 20)),
}


def compute_factor_vector(df: pd.DataFrame) -> dict[str, float | None]:
    """Evaluate every factor in :data:`FACTORS` for one symbol's OHLCV.

    Parameters
    ----------
    df:
        OHLCV frame with the :data:`REQUIRED_COLUMNS`, oldest bar first.

    Returns
    -------
    dict
        ``{factor_name: value_or_None}`` for every registered factor. A
        factor returns ``None`` when its lookback is unmet; a too-short
        frame therefore yields an all-``None`` vector rather than raising.

    Raises
    ------
    ValueError
        If ``df`` is missing any required OHLCV column — a programming error
        in the caller, distinct from the benign "not enough bars" case.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")
    return {name: spec.fn(df) for name, spec in FACTORS.items()}


def composite_momentum_score(df: pd.DataFrame) -> float | None:
    """A trivial composite: average of the available momentum ROC factors.

    Combines ``ROC5 / ROC20 / ROC60`` into a single mean of whichever are
    defined (skipping ``None`` warmup factors). Returns ``None`` only when
    *all three* are unavailable. This is a deliberately simple aggregation —
    a real factor model would z-score and weight — surfaced as a convenience
    summary, not a trading signal.
    """
    parts = [roc(df, w) for w in (5, 20, 60)]
    available = [p for p in parts if p is not None]
    if not available:
        return None
    return _finite(float(np.mean(available)))
