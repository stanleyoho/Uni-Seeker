"""Unit tests for the pure live-indicator computation — A2 v1.

These exercise ``compute_live_indicators`` in isolation (no DB / no network):
  - latest-value extraction across the TA-Lib warmup window
  - golden / death / flat MA-cross classification
  - change + percent derivation from the live price vs prev close
  - graceful degradation: empty history, no live price, single-bar history
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.watchlist.live_indicators import (
    CROSS_DEATH,
    CROSS_GOLDEN,
    compute_live_indicators,
)


def _rising(n: int) -> list[float]:
    """A strictly rising close series → short MA > long MA (golden)."""
    return [100.0 + i for i in range(n)]


def _falling(n: int) -> list[float]:
    """A strictly falling close series → short MA < long MA (death)."""
    return [200.0 - i for i in range(n)]


def test_rising_series_is_golden_cross_and_rsi_high() -> None:
    snap = compute_live_indicators(_rising(40))
    assert snap.ma_cross == CROSS_GOLDEN
    # Short MA above long MA on a monotonic uptrend.
    assert snap.ma_short is not None
    assert snap.ma_long is not None
    assert snap.ma_short > snap.ma_long
    # RSI of a pure uptrend pins at 100.
    assert snap.rsi == Decimal("100")
    # Price (latest close, since no live price given) sits above the long MA.
    assert snap.pct_from_ma_long is not None
    assert snap.pct_from_ma_long > 0


def test_falling_series_is_death_cross() -> None:
    snap = compute_live_indicators(_falling(40))
    assert snap.ma_cross == CROSS_DEATH
    assert snap.ma_short is not None
    assert snap.ma_long is not None
    assert snap.ma_short < snap.ma_long
    # Below long MA → negative distance.
    assert snap.pct_from_ma_long is not None
    assert snap.pct_from_ma_long < 0


def test_live_price_drives_change_and_percent() -> None:
    # Live price overrides the latest close for change / ratio math.
    snap = compute_live_indicators(
        _rising(30),
        last_price=Decimal("150"),
        prev_close=Decimal("120"),
    )
    assert snap.last_price == Decimal("150")
    assert snap.prev_close == Decimal("120")
    assert snap.change == Decimal("30")
    # 30 / 120 * 100 = 25%.
    assert snap.change_percent == Decimal("25")


def test_prev_close_falls_back_to_second_last_close() -> None:
    closes = [10.0, 12.0]  # last=12, prev=10
    snap = compute_live_indicators(closes)
    assert snap.last_price == Decimal("12.0")
    assert snap.prev_close == Decimal("10.0")
    assert snap.change == Decimal("2.0")


def test_empty_history_returns_all_none() -> None:
    snap = compute_live_indicators([])
    assert snap.last_price is None
    assert snap.rsi is None
    assert snap.ma_short is None
    assert snap.ma_long is None
    assert snap.ma_cross is None
    assert snap.pct_from_ma_long is None
    assert snap.change is None


def test_no_live_price_uses_latest_close_but_keeps_history_context() -> None:
    # Enough bars for the long MA but no feed: we still get MA context and a
    # close-derived price, with change vs the prior close.
    snap = compute_live_indicators(_rising(25), last_price=None, prev_close=None)
    assert snap.last_price == Decimal("124.0")  # 100 + 24
    assert snap.ma_long is not None
    assert snap.ma_cross == CROSS_GOLDEN
    # change vs the second-to-last close (123) = +1.
    assert snap.change == Decimal("1.0")


def test_short_history_below_long_window_yields_none_ma_long() -> None:
    # 5 bars: short SMA(5) computes, long SMA(20) does not → cross is None.
    snap = compute_live_indicators(_rising(5))
    assert snap.ma_short is not None
    assert snap.ma_long is None
    assert snap.ma_cross is None
    assert snap.pct_from_ma_long is None
