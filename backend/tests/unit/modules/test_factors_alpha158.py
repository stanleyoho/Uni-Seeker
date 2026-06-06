"""Unit tests for the Alpha158-style factor set.

Each test drives a factor with a *hand-computable* OHLCV frame and asserts
the exact expected value, so a regression in any formula fails here with a
clear numeric diff rather than via an opaque downstream consumer.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.modules.factors import (
    FACTORS,
    beta_to_index,
    composite_momentum_score,
    compute_factor_vector,
    klen,
    klow,
    kmid,
    kup,
    ma_ratio,
    max_position,
    min_position,
    roc,
    rsi_factor,
    std_factor,
    volume_ratio,
    williams_r,
)


def _frame(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    """Build an OHLCV frame from (open, high, low, close, volume) tuples."""
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


# ── Candle geometry ────────────────────────────────────────────────────────


def test_kmid_bullish_body() -> None:
    # open=100, close=110 -> (110-100)/100 = 0.1
    df = _frame([(100.0, 115.0, 95.0, 110.0, 1000.0)])
    assert kmid(df) == pytest.approx(0.1)


def test_klen_full_range() -> None:
    # (high-low)/open = (115-95)/100 = 0.2
    df = _frame([(100.0, 115.0, 95.0, 110.0, 1000.0)])
    assert klen(df) == pytest.approx(0.2)


def test_kup_upper_shadow() -> None:
    # (high - max(open, close))/open = (115 - 110)/100 = 0.05
    df = _frame([(100.0, 115.0, 95.0, 110.0, 1000.0)])
    assert kup(df) == pytest.approx(0.05)


def test_klow_lower_shadow() -> None:
    # (min(open, close) - low)/open = (100 - 95)/100 = 0.05
    df = _frame([(100.0, 115.0, 95.0, 110.0, 1000.0)])
    assert klow(df) == pytest.approx(0.05)


def test_candle_factors_none_on_zero_open() -> None:
    df = _frame([(0.0, 1.0, 0.0, 0.5, 1.0)])
    assert kmid(df) is None
    assert klen(df) is None
    assert kup(df) is None
    assert klow(df) is None


# ── Momentum / ROC ─────────────────────────────────────────────────────────


def test_roc_simple_return() -> None:
    # 6 bars; close 5 bars ago = 100, latest = 110 -> 110/100 - 1 = 0.1
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    assert roc(df, 5) == pytest.approx(0.1)


def test_roc_insufficient_lookback() -> None:
    df = _frame([(100.0, 100.0, 100.0, 100.0, 1.0)] * 3)
    assert roc(df, 5) is None


def test_ma_ratio() -> None:
    # mean([10,20,30,40,50]) = 30, latest close = 50 -> 30/50 = 0.6
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    assert ma_ratio(df, 5) == pytest.approx(0.6)


# ── Volatility ─────────────────────────────────────────────────────────────


def test_std_factor_population_std() -> None:
    closes = [10.0, 12.0, 14.0, 16.0, 18.0]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    expected_std = float(np.std(closes, ddof=0))  # population std
    # Factor output is rounded to 6 dp by _finite, so allow that tolerance.
    assert std_factor(df, 5) == pytest.approx(expected_std / 18.0, abs=1e-6)


# ── Volume ─────────────────────────────────────────────────────────────────


def test_volume_ratio() -> None:
    # mean([100,200,300]) = 200, latest volume = 300 -> 200/300
    vols = [100.0, 200.0, 300.0]
    df = _frame([(10.0, 10.0, 10.0, 10.0, v) for v in vols])
    assert volume_ratio(df, 3) == pytest.approx(200.0 / 300.0)


def test_volume_ratio_none_on_zero_latest_volume() -> None:
    df = _frame([(10.0, 10.0, 10.0, 10.0, 100.0), (10.0, 10.0, 10.0, 10.0, 0.0)])
    assert volume_ratio(df, 2) is None


# ── Oscillators ────────────────────────────────────────────────────────────


def test_rsi_all_gains_is_100() -> None:
    # Strictly increasing closes -> RSI saturates at 100.
    closes = [float(i) for i in range(1, 30)]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    result = rsi_factor(df, 14)
    assert result is not None
    assert result == pytest.approx(100.0, abs=1e-6)


def test_williams_r_at_top_of_range() -> None:
    # Latest close == highest high -> %R == 0.
    df = _frame(
        [
            (10.0, 12.0, 8.0, 11.0, 1.0),
            (11.0, 14.0, 9.0, 13.0, 1.0),
            (13.0, 16.0, 10.0, 16.0, 1.0),  # close == high == window max
        ]
    )
    assert williams_r(df, 3) == pytest.approx(0.0)


def test_williams_r_at_bottom_of_range() -> None:
    # Latest close == lowest low -> %R == -100.
    df = _frame(
        [
            (10.0, 12.0, 8.0, 11.0, 1.0),
            (11.0, 14.0, 9.0, 13.0, 1.0),
            (13.0, 16.0, 6.0, 6.0, 1.0),  # close == low == window min
        ]
    )
    assert williams_r(df, 3) == pytest.approx(-100.0)


# ── Range position ─────────────────────────────────────────────────────────


def test_max_position_peak_is_latest() -> None:
    # Highs increasing; peak at last index (idx 4) -> 4/5 = 0.8
    highs = [10.0, 11.0, 12.0, 13.0, 14.0]
    df = _frame([(h, h, h - 1, h, 1.0) for h in highs])
    assert max_position(df, 5) == pytest.approx(0.8)


def test_min_position_trough_is_oldest() -> None:
    # Lows increasing; trough at first index (idx 0) -> 0/5 = 0.0
    lows = [5.0, 6.0, 7.0, 8.0, 9.0]
    df = _frame([(low + 1, low + 2, low, low + 1, 1.0) for low in lows])
    assert min_position(df, 5) == pytest.approx(0.0)


# ── Beta ───────────────────────────────────────────────────────────────────


def test_beta_perfectly_correlated_is_one() -> None:
    # Symbol == index -> beta of an asset against itself is exactly 1.
    closes = [100.0, 101.0, 99.0, 102.0, 103.0, 101.0, 104.0]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    assert beta_to_index(df, df, window=5) == pytest.approx(1.0)


def test_beta_double_amplitude_is_two() -> None:
    # Symbol return == 2x index return each day -> beta == 2.
    idx_closes = [100.0, 110.0, 99.0, 108.9, 119.79, 107.811]
    # Build symbol so its daily simple return is exactly twice the index's.
    idx = np.array(idx_closes)
    idx_ret = idx[1:] / idx[:-1] - 1.0
    sym = [100.0]
    for r in idx_ret:
        sym.append(sym[-1] * (1.0 + 2.0 * r))
    sym_df = _frame([(c, c, c, c, 1.0) for c in sym])
    idx_df = _frame([(c, c, c, c, 1.0) for c in idx_closes])
    assert beta_to_index(sym_df, idx_df, window=5) == pytest.approx(2.0, abs=1e-6)


def test_beta_insufficient_data() -> None:
    df = _frame([(100.0, 100.0, 100.0, 100.0, 1.0)] * 3)
    assert beta_to_index(df, df, window=60) is None


# ── Composite + registry ───────────────────────────────────────────────────


def test_composite_momentum_averages_available_roc() -> None:
    # 6 bars: ROC5 defined, ROC20/ROC60 None -> composite == ROC5.
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    df = _frame([(c, c, c, c, 1.0) for c in closes])
    assert composite_momentum_score(df) == pytest.approx(0.1)


def test_compute_factor_vector_keys_match_registry() -> None:
    closes = [float(100 + i) for i in range(70)]
    df = _frame([(c, c + 1, c - 1, c, 1000.0) for c in closes])
    vec = compute_factor_vector(df)
    assert set(vec.keys()) == set(FACTORS.keys())
    # With 70 bars all windows are warmed up -> no None except possibly none.
    assert all(v is None or math.isfinite(v) for v in vec.values())


def test_compute_factor_vector_missing_column_raises() -> None:
    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})
    with pytest.raises(ValueError, match="missing columns"):
        compute_factor_vector(df)


def test_compute_factor_vector_short_frame_all_none_for_windowed() -> None:
    # Single bar: candle factors compute, windowed factors are None.
    df = _frame([(100.0, 110.0, 90.0, 105.0, 1000.0)])
    vec = compute_factor_vector(df)
    assert vec["KMID"] is not None
    assert vec["ROC5"] is None
    assert vec["STD20"] is None


def test_factor_registry_has_expected_factors() -> None:
    # Guard the public surface: the bounded v1 set must stay intact.
    expected = {
        "KMID",
        "KLEN",
        "KUP",
        "KLOW",
        "ROC5",
        "ROC20",
        "ROC60",
        "MA5",
        "MA20",
        "STD20",
        "VMA5",
        "RSI14",
        "WILLR14",
        "IMAX20",
        "IMIN20",
    }
    assert set(FACTORS.keys()) == expected
    # Every spec must carry a non-empty formula (living documentation).
    assert all(spec.formula for spec in FACTORS.values())
