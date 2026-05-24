"""Unit tests for `app.modules.portfolio.pnl`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §7.

Coverage (~12 cases):
  P01 unrealized — gain
  P02 unrealized — loss
  P03 unrealized — qty == 0 (no position)
  P04 unrealized — avg_cost == 0 (div-by-zero guard)
  P05 daily_change — normal positive delta
  P06 daily_change — prev_close == 0 (div-by-zero guard)
  P07 daily_change — last == prev (delta = 0)
  P08 summarize — mixed gain/loss multi-position
  P09 summarize — empty positions
  P10 summarize — all qty == 0
  P11 summarize — total_cost == 0 (gain_simple_pct guard)
  P12 summarize — Q6 (A) gain = total_value - total_cost
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.portfolio.pnl import (
    daily_change,
    summarize,
    unrealized,
)


# P01 — unrealized gain
def test_P01_unrealized_gain():
    res = unrealized(
        qty=Decimal("100"),
        avg_cost=Decimal("100"),
        last_price=Decimal("150"),
    )
    assert res.unrealized_pnl == Decimal("5000")
    assert res.unrealized_pnl_pct == Decimal("0.5")


# P02 — unrealized loss
def test_P02_unrealized_loss():
    res = unrealized(
        qty=Decimal("100"),
        avg_cost=Decimal("100"),
        last_price=Decimal("80"),
    )
    assert res.unrealized_pnl == Decimal("-2000")
    assert res.unrealized_pnl_pct == Decimal("-0.2")


# P03 — qty == 0 zeroes everything
def test_P03_unrealized_qty_zero():
    res = unrealized(
        qty=Decimal("0"),
        avg_cost=Decimal("100"),
        last_price=Decimal("150"),
    )
    assert res.qty == Decimal("0")
    assert res.unrealized_pnl == Decimal("0")
    assert res.unrealized_pnl_pct == Decimal("0")


# P04 — avg_cost == 0 → pct guard
def test_P04_unrealized_avg_cost_zero():
    res = unrealized(
        qty=Decimal("100"),
        avg_cost=Decimal("0"),
        last_price=Decimal("50"),
    )
    assert res.unrealized_pnl == Decimal("5000")
    # division would be 5000 / 0 — guard returns 0
    assert res.unrealized_pnl_pct == Decimal("0")


# P05 — daily_change normal
def test_P05_daily_change_normal():
    res = daily_change(
        qty=Decimal("10"),
        last_price=Decimal("110"),
        prev_close=Decimal("100"),
    )
    assert res.delta_per_share == Decimal("10")
    assert res.delta_total == Decimal("100")
    assert res.delta_pct == Decimal("0.1")


# P06 — prev_close == 0 → pct guard
def test_P06_daily_change_prev_close_zero():
    res = daily_change(
        qty=Decimal("10"),
        last_price=Decimal("50"),
        prev_close=Decimal("0"),
    )
    assert res.delta_per_share == Decimal("50")
    assert res.delta_total == Decimal("500")
    assert res.delta_pct == Decimal("0")  # guarded


# P07 — last == prev → all-zero delta
def test_P07_daily_change_no_move():
    res = daily_change(
        qty=Decimal("10"),
        last_price=Decimal("100"),
        prev_close=Decimal("100"),
    )
    assert res.delta_per_share == Decimal("0")
    assert res.delta_total == Decimal("0")
    assert res.delta_pct == Decimal("0")


# P08 — summarize: mixed gain + loss across positions
def test_P08_summarize_mixed():
    # Position A: qty=100, avg=100, last=150, prev=140 → +5000 unreal, +1000 daily
    # Position B: qty=50,  avg=200, last=180, prev=190 → -1000 unreal, -500  daily
    positions = [
        (Decimal("100"), Decimal("100"), Decimal("150"), Decimal("140")),
        (Decimal("50"), Decimal("200"), Decimal("180"), Decimal("190")),
    ]
    s = summarize(positions)
    assert s.total_cost == Decimal("20000")  # 100*100 + 50*200
    assert s.total_value == Decimal("24000")  # 100*150 + 50*180
    assert s.total_unrealized_pnl == Decimal("4000")
    assert s.total_daily_change == Decimal("500")  # 1000 + (-500)
    assert s.gain_simple == Decimal("4000")
    assert s.gain_simple_pct == Decimal("0.2")


# P09 — empty list
def test_P09_summarize_empty():
    s = summarize([])
    assert s.total_cost == Decimal("0")
    assert s.total_value == Decimal("0")
    assert s.total_unrealized_pnl == Decimal("0")
    assert s.total_daily_change == Decimal("0")
    assert s.gain_simple == Decimal("0")
    assert s.gain_simple_pct == Decimal("0")


# P10 — all qty == 0
def test_P10_summarize_all_zero_qty():
    positions = [
        (Decimal("0"), Decimal("100"), Decimal("150"), Decimal("140")),
        (Decimal("0"), Decimal("200"), Decimal("180"), Decimal("190")),
    ]
    s = summarize(positions)
    assert s.total_cost == Decimal("0")
    assert s.gain_simple == Decimal("0")
    assert s.gain_simple_pct == Decimal("0")


# P11 — gain_simple_pct guard when total_cost == 0
@pytest.mark.parametrize(
    "positions",
    [
        # All free shares (avg_cost = 0)
        [(Decimal("100"), Decimal("0"), Decimal("50"), Decimal("40"))],
    ],
)
def test_P11_summarize_total_cost_zero_pct_guard(positions):
    s = summarize(positions)
    assert s.total_cost == Decimal("0")
    assert s.gain_simple == Decimal("5000")  # 100*50 - 0
    # gain_simple / 0 would explode — guard returns 0
    assert s.gain_simple_pct == Decimal("0")


# P12 — Q6 (A) verifies gain_simple = total_value - total_cost (spec §7.4)
def test_P12_summarize_q6_gain_definition():
    # Single position; gain_simple must equal MV - cost basis identically
    positions = [
        (Decimal("200"), Decimal("75"), Decimal("90"), Decimal("85")),
    ]
    s = summarize(positions)
    # MV = 200*90 = 18000; Cost = 200*75 = 15000; gain = 3000
    assert s.total_value == Decimal("18000")
    assert s.total_cost == Decimal("15000")
    assert s.gain_simple == s.total_value - s.total_cost
    assert s.gain_simple == Decimal("3000")
    assert s.gain_simple_pct == Decimal("0.2")
