"""Unit tests for the 四大買賣點 pure calculator.

Covers every one of the 8 points (each trigger + non-trigger), the
bias-pivot gate, the verdict logic, and the helper functions
(``_moving_average`` / ``_continuous`` / ``_bias_pivot``).

Construction strategy
=====================
twstock gates every buy/sell point behind a *bias-ratio pivot* on the
(MA3 − MA6) spread:

  - The BUY gate fires only when the spread recently bottomed BELOW zero
    and is curling back up — which means MA3 < MA6 in the recent window.
  - The SELL gate fires only when the spread recently topped ABOVE zero.

A structural consequence (documented in calculator.py): **point 4
(三日均價 ⋛ 六日均價) can never co-occur with its own gate** — the buy gate
requires MA3 < MA6, but buy_4 requires MA3 > MA6. twstock keeps point 4 in
its WHY list, but the gate makes it unreachable through the gated output.
So points 1/2/3 are tested through the full gated ``compute_best_four_point``,
and point 4 is tested through the internal ``_buy_points`` / ``_sell_points``
flag functions directly (which is exactly twstock's ``best_buy_4`` /
``best_sell_4`` predicate).

``_BUY_GATE_CLOSES`` / ``_SELL_GATE_CLOSES`` are series verified to pass the
respective gate with ``continuous(MA3) == ±1`` (so buy_3 / sell_3 fire).
``_SELL_GATE_CLOSES`` is the (100 − x) mirror of the buy series.
"""

from __future__ import annotations

from app.modules.best_four_point import OHLCVSeries, compute_best_four_point
from app.modules.best_four_point.calculator import (
    BEST_BUY_WHY,
    BEST_SELL_WHY,
    MIN_BARS,
    VERDICT_BUY,
    VERDICT_HOLD,
    VERDICT_SELL,
    _bias_pivot,
    _buy_points,
    _continuous,
    _moving_average,
    _sell_points,
)


def _make(
    closes: list[float],
    *,
    opens: list[float] | None = None,
    volumes: list[float] | None = None,
) -> OHLCVSeries:
    n = len(closes)
    return OHLCVSeries(
        opens=opens if opens is not None else list(closes),
        highs=[c + 1 for c in closes],
        lows=[c - 1 for c in closes],
        closes=closes,
        volumes=volumes if volumes is not None else [1000.0] * n,
    )


# Verified to pass the BUY (mins) bias-pivot gate with continuous(MA3) == 1.
_BUY_GATE_CLOSES = [50.0, 46.4, 49.4, 50.0, 47.6, 47.6, 47.5, 46.4, 45.2, 45.5, 46.5]
# (100 − x) mirror → passes the SELL (plus) gate with continuous(MA3) == -1.
_SELL_GATE_CLOSES = [round(100 - x, 1) for x in _BUY_GATE_CLOSES]


# ── Helper functions ──────────────────────────────────────────────────────


def test_moving_average_basic() -> None:
    assert _moving_average([1, 2, 3, 4], 3) == [2.0, 3.0]


def test_moving_average_too_short_returns_empty() -> None:
    assert _moving_average([1, 2], 3) == []


def test_continuous_up_run() -> None:
    assert _continuous([1, 2, 3, 4, 5]) == 4


def test_continuous_single_up_step() -> None:
    assert _continuous([5, 4, 3, 4]) == 1


def test_continuous_down_run() -> None:
    assert _continuous([5, 4, 3, 2]) == -3


def test_continuous_too_short_is_zero() -> None:
    assert _continuous([5]) == 0


def test_bias_pivot_buy_gate_fires_on_recent_bottom() -> None:
    # All 5 negative, min within last 4 bars but not today (idx 2).
    spread = [-1.0, -2.0, -3.0, -2.0, -1.0]
    assert _bias_pivot(spread, position=False) is True


def test_bias_pivot_buy_gate_rejects_positive_spread() -> None:
    # max(sample) >= 0 → pre_check fails → no buy pivot.
    spread = [1.0, 2.0, 1.5, 1.0, 0.5]
    assert _bias_pivot(spread, position=False) is False


def test_bias_pivot_buy_gate_rejects_bottom_today() -> None:
    # Min is today (idx 4) → excluded.
    spread = [-1.0, -2.0, -2.5, -3.0, -4.0]
    assert _bias_pivot(spread, position=False) is False


def test_bias_pivot_sell_gate_fires_on_recent_top() -> None:
    spread = [1.0, 2.0, 3.0, 2.0, 1.0]
    assert _bias_pivot(spread, position=True) is True


# ── Buy points 1/2/3 via gated compute (each trigger + non-trigger) ───────


def test_buy_point_1_volume_up_close_above_open() -> None:
    closes = list(_BUY_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] - 5  # close > open today
    volumes = [1000.0] * n
    volumes[-1] = 5000.0  # vol up vs prior
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_BUY_WHY[0] in res.buy_points


def test_buy_point_1_non_trigger_when_close_below_open() -> None:
    closes = list(_BUY_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] + 5  # close < open today → buy_1 false
    opens[-2] = closes[-1] + 5  # also break buy_2
    volumes = [1000.0] * n
    volumes[-1] = 5000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_BUY_WHY[0] not in res.buy_points


def test_buy_point_2_volume_down_close_above_prev_open() -> None:
    closes = list(_BUY_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-2] = closes[-1] - 5  # close[-1] > open[-2]
    opens[-1] = closes[-1] + 5  # break buy_1
    volumes = [1000.0] * n
    volumes[-1] = 500.0
    volumes[-2] = 1000.0  # vol down
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_BUY_WHY[1] in res.buy_points
    assert BEST_BUY_WHY[0] not in res.buy_points


def test_buy_point_2_non_trigger_when_volume_up() -> None:
    closes = list(_BUY_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-2] = closes[-1] - 5
    volumes = [1000.0] * n
    volumes[-1] = 5000.0  # vol UP → buy_2 false
    volumes[-2] = 1000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_BUY_WHY[1] not in res.buy_points


def test_buy_point_3_ma3_turns_up() -> None:
    # _BUY_GATE_CLOSES has continuous(MA3) == 1 (verified).
    res = compute_best_four_point(_make(_BUY_GATE_CLOSES))
    assert BEST_BUY_WHY[2] in res.buy_points


def test_buy_point_3_non_trigger_when_ma3_falling() -> None:
    closes = [60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40]
    res = compute_best_four_point(_make(closes))
    assert BEST_BUY_WHY[2] not in res.buy_points


def test_buy_point_4_ma3_above_ma6_via_flags() -> None:
    # Point 4 cannot co-occur with the buy gate (see module docstring), so
    # test the predicate directly — exactly twstock's ``best_buy_4``.
    closes = [40.0, 42, 44, 46, 48, 50, 52, 54]  # rising → MA3 > MA6
    ma3 = _moving_average(closes, 3)
    ma6 = _moving_average(closes, 6)
    flags = _buy_points(_make(closes), ma3, ma6)
    assert flags[3] is True


def test_buy_point_4_non_trigger_when_ma3_below_ma6_via_flags() -> None:
    closes = [54.0, 52, 50, 48, 46, 44, 42, 40]  # falling → MA3 < MA6
    ma3 = _moving_average(closes, 3)
    ma6 = _moving_average(closes, 6)
    flags = _buy_points(_make(closes), ma3, ma6)
    assert flags[3] is False


# ── Sell points 1/2/3 via gated compute (each trigger + non-trigger) ──────


def test_sell_point_1_volume_up_close_below_open() -> None:
    closes = list(_SELL_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] + 5  # close < open today
    volumes = [1000.0] * n
    volumes[-1] = 5000.0  # vol up
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_SELL_WHY[0] in res.sell_points


def test_sell_point_1_non_trigger_when_close_above_open() -> None:
    closes = list(_SELL_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] - 5  # close > open today → sell_1 false
    opens[-2] = closes[-1] - 5  # break sell_2
    volumes = [1000.0] * n
    volumes[-1] = 5000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_SELL_WHY[0] not in res.sell_points


def test_sell_point_2_volume_down_close_below_prev_open() -> None:
    closes = list(_SELL_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-2] = closes[-1] + 5  # close[-1] < open[-2]
    opens[-1] = closes[-1] - 5  # break sell_1
    volumes = [1000.0] * n
    volumes[-1] = 500.0
    volumes[-2] = 1000.0  # vol down
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_SELL_WHY[1] in res.sell_points
    assert BEST_SELL_WHY[0] not in res.sell_points


def test_sell_point_2_non_trigger_when_volume_up() -> None:
    closes = list(_SELL_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-2] = closes[-1] + 5
    volumes = [1000.0] * n
    volumes[-1] = 5000.0  # vol UP → sell_2 false
    volumes[-2] = 1000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert BEST_SELL_WHY[1] not in res.sell_points


def test_sell_point_3_ma3_turns_down() -> None:
    # _SELL_GATE_CLOSES has continuous(MA3) == -1 (verified).
    res = compute_best_four_point(_make(_SELL_GATE_CLOSES))
    assert BEST_SELL_WHY[2] in res.sell_points


def test_sell_point_3_non_trigger_when_ma3_rising() -> None:
    closes = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60]
    res = compute_best_four_point(_make(closes))
    assert BEST_SELL_WHY[2] not in res.sell_points


def test_sell_point_4_ma3_below_ma6_via_flags() -> None:
    closes = [54.0, 52, 50, 48, 46, 44, 42, 40]  # falling → MA3 < MA6
    ma3 = _moving_average(closes, 3)
    ma6 = _moving_average(closes, 6)
    flags = _sell_points(_make(closes), ma3, ma6)
    assert flags[3] is True


def test_sell_point_4_non_trigger_when_ma3_above_ma6_via_flags() -> None:
    closes = [40.0, 42, 44, 46, 48, 50, 52, 54]  # rising → MA3 > MA6
    ma3 = _moving_average(closes, 3)
    ma6 = _moving_average(closes, 6)
    flags = _sell_points(_make(closes), ma3, ma6)
    assert flags[3] is False


# ── Verdict logic ─────────────────────────────────────────────────────────


def test_verdict_buy_when_buy_points_present() -> None:
    closes = list(_BUY_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] - 5
    volumes = [1000.0] * n
    volumes[-1] = 5000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert res.verdict == VERDICT_BUY
    assert res.net_score >= 1
    assert res.has_signal is True


def test_verdict_sell_when_sell_points_present() -> None:
    closes = list(_SELL_GATE_CLOSES)
    n = len(closes)
    opens = list(closes)
    opens[-1] = closes[-1] + 5
    volumes = [1000.0] * n
    volumes[-1] = 5000.0
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert res.verdict == VERDICT_SELL
    assert res.net_score <= -1


def test_verdict_hold_when_bias_gate_blocks() -> None:
    # Steady uptrend: spread positive & monotone → buy gate (needs a recent
    # BELOW-zero bottom) cannot fire; no points surface → 觀望.
    closes = [40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60]
    n = len(closes)
    opens = [c - 1 for c in closes]
    volumes = [1000.0 + i for i in range(n)]
    res = compute_best_four_point(_make(closes, opens=opens, volumes=volumes))
    assert res.verdict == VERDICT_HOLD
    assert res.buy_points == []
    assert res.sell_points == []
    assert res.has_signal is False


# ── Guard rails ───────────────────────────────────────────────────────────


def test_insufficient_bars_returns_hold_with_note() -> None:
    closes = [1.0, 2.0, 3.0]  # < MIN_BARS
    res = compute_best_four_point(_make(closes))
    assert res.verdict == VERDICT_HOLD
    assert "insufficient" in res.note
    assert len(closes) < MIN_BARS


def test_inconsistent_series_returns_hold_with_note() -> None:
    bad = OHLCVSeries(
        opens=[1.0, 2.0],
        highs=[1.0],
        lows=[1.0, 2.0],
        closes=[1.0, 2.0],
        volumes=[1.0, 2.0],
    )
    res = compute_best_four_point(bad)
    assert res.verdict == VERDICT_HOLD
    assert "mismatch" in res.note
