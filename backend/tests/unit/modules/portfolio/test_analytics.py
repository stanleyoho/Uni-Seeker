"""Unit tests for `app.modules.portfolio.analytics`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11
+ Phase 5 brief. ~16 cases covering:

  TWR
    A01 simple buy-and-hold, no flow
    A02 with intermediate deposit
    A03 zero start_value gets skipped
    A04 annualised return for a 1-year window matches geometric extrapolation
    A05 empty snapshots → (0, 0)
    A06 single snapshot → (0, 0)

  Sharpe
    A07 < 2 returns → None
    A08 constant returns (stdev == 0) → None
    A09 positive excess return → positive Sharpe
    A10 returns matching rf exactly → ratio ≈ 0

  Max drawdown
    A11 monotonic increase → 0
    A12 V-shape → captures trough
    A13 W-shape → picks deepest of two valleys
    A14 empty → (0, 0)
    A15 pct calculation matches |trough-peak|/peak
    A16 single element → (0, 0)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.portfolio.analytics import (
    CashFlow,
    NavSnapshot,
    compute_max_drawdown,
    compute_sharpe,
    compute_twr,
    daily_returns_from_navs,
)


# ── TWR ─────────────────────────────────────────────────────────────────────


def test_A01_twr_simple_buy_hold_no_flow():
    snaps = [
        NavSnapshot(date(2026, 1, 1), Decimal("100"), Decimal("100")),
        NavSnapshot(date(2026, 1, 31), Decimal("110"), Decimal("100")),
    ]
    twr, _ann = compute_twr(snaps, [])
    # (110 - 100 - 0) / 100 = 0.10
    assert twr == Decimal("0.1")


def test_A02_twr_with_intermediate_deposit():
    """Deposit of 50 on day 15 must be excluded from the return numerator.

    NAV day 1 = 100, NAV day 15 = 150 (after the deposit), NAV day 30 = 165.
    Window 1: (150 - 100 - 50) / 100 = 0.00   (deposit accounts for the lift)
    Window 2: (165 - 150 - 0)  / 150 = 0.10
    TWR = (1.00)(1.10) - 1 = 0.10
    """
    snaps = [
        NavSnapshot(date(2026, 1, 1), Decimal("100"), Decimal("100")),
        NavSnapshot(date(2026, 1, 15), Decimal("150"), Decimal("150")),
        NavSnapshot(date(2026, 1, 30), Decimal("165"), Decimal("150")),
    ]
    flows = [CashFlow(date(2026, 1, 15), Decimal("50"))]
    twr, _ann = compute_twr(snaps, flows)
    assert twr == Decimal("0.1")


def test_A03_twr_handles_zero_start_value():
    """Sub-period with `start_value == 0` is silently skipped."""
    snaps = [
        NavSnapshot(date(2026, 1, 1), Decimal("0"), Decimal("0")),
        NavSnapshot(date(2026, 1, 10), Decimal("100"), Decimal("100")),
        NavSnapshot(date(2026, 1, 20), Decimal("110"), Decimal("100")),
    ]
    flows = [CashFlow(date(2026, 1, 10), Decimal("100"))]
    twr, _ann = compute_twr(snaps, flows)
    # Window 1 skipped, Window 2 = (110-100)/100 = 0.10
    assert twr == Decimal("0.1")


def test_A04_twr_annualized_correct_for_1_year():
    """A 1.10x growth over exactly 365 days should annualise to 0.10."""
    snaps = [
        NavSnapshot(date(2026, 1, 1), Decimal("100"), Decimal("100")),
        NavSnapshot(date(2027, 1, 1), Decimal("110"), Decimal("100")),
    ]
    twr, ann = compute_twr(snaps, [])
    assert twr == Decimal("0.1")
    # ann == (1.10)^(365/365) - 1 = 0.10 (within Decimal precision)
    assert abs(ann - Decimal("0.1")) < Decimal("1E-10")


def test_A05_twr_empty():
    twr, ann = compute_twr([], [])
    assert twr == Decimal("0")
    assert ann == Decimal("0")


def test_A06_twr_single_snapshot():
    snaps = [NavSnapshot(date(2026, 1, 1), Decimal("100"), Decimal("100"))]
    twr, ann = compute_twr(snaps, [])
    assert twr == Decimal("0")
    assert ann == Decimal("0")


# ── Sharpe ──────────────────────────────────────────────────────────────────


def test_A07_sharpe_too_few_returns_returns_none():
    assert compute_sharpe([]) is None
    assert compute_sharpe([Decimal("0.01")]) is None


def test_A08_sharpe_constant_returns_returns_none_zero_stdev():
    # All returns identical → variance = 0 → no Sharpe.
    assert compute_sharpe([Decimal("0.01")] * 10) is None


def test_A09_sharpe_positive_excess_return():
    """Realised mean > rf → positive Sharpe.

    Daily returns averaging well above the 0.02/252 ≈ 7.9e-5 risk-free
    rate must yield a positive ratio. We don't pin the exact number —
    just the sign and order of magnitude.
    """
    # Five identical-but-not-quite returns so stdev != 0.
    returns = [
        Decimal("0.005"),
        Decimal("0.004"),
        Decimal("0.006"),
        Decimal("0.005"),
        Decimal("0.004"),
    ]
    sharpe = compute_sharpe(returns)
    assert sharpe is not None
    assert sharpe > Decimal("0")
    # Sanity: ~ ((0.0048 - 7.9e-5) / 8e-4) * sqrt(252) ≈ 93+
    assert sharpe > Decimal("10")


def test_A10_sharpe_returns_close_to_rf():
    """Returns clustered at rf_daily → tiny / near-zero excess."""
    rf_daily = Decimal("0.02") / Decimal("252")
    # Two-point series so stdev != 0 but mean ≈ rf_daily.
    returns = [rf_daily + Decimal("1E-10"), rf_daily - Decimal("1E-10")]
    sharpe = compute_sharpe(returns)
    assert sharpe is not None
    # Excess mean ≈ 0 so Sharpe ≈ 0.
    assert abs(sharpe) < Decimal("0.01")


# ── Max drawdown ────────────────────────────────────────────────────────────


def test_A11_max_drawdown_monotonic_increase_zero():
    navs = [Decimal(str(v)) for v in (100, 110, 120, 130, 140)]
    dd, pct = compute_max_drawdown(navs)
    assert dd == Decimal("0")
    assert pct == Decimal("0")


def test_A12_max_drawdown_v_shape():
    # Peak 100, trough 60, recovery to 90.
    navs = [Decimal(str(v)) for v in (100, 80, 60, 75, 90)]
    dd, pct = compute_max_drawdown(navs)
    assert dd == Decimal("-40")
    # -40 / 100 = -0.4
    assert pct == Decimal("-0.4")


def test_A13_max_drawdown_w_shape_picks_deepest():
    """Two valleys — must pick the deeper one (peak resets on new highs)."""
    navs = [
        Decimal("100"),  # peak 1
        Decimal("80"),   # dd1 = -20 (-20 %)
        Decimal("120"),  # new peak
        Decimal("70"),   # dd2 = -50 (-41.67 %) ← deeper
        Decimal("90"),
    ]
    dd, pct = compute_max_drawdown(navs)
    assert dd == Decimal("-50")
    assert pct == Decimal("-50") / Decimal("120")


def test_A14_max_drawdown_empty():
    dd, pct = compute_max_drawdown([])
    assert dd == Decimal("0")
    assert pct == Decimal("0")


def test_A15_max_drawdown_pct_calculation():
    navs = [Decimal("200"), Decimal("100")]
    dd, pct = compute_max_drawdown(navs)
    assert dd == Decimal("-100")
    assert pct == Decimal("-0.5")


def test_A16_max_drawdown_single_element():
    dd, pct = compute_max_drawdown([Decimal("100")])
    assert dd == Decimal("0")
    assert pct == Decimal("0")


# ── helper: daily_returns_from_navs ─────────────────────────────────────────


def test_A17_daily_returns_from_navs():
    """Sanity check the NAV → daily-return adapter used by AnalyticsService."""
    snaps = [
        NavSnapshot(date(2026, 1, 1), Decimal("100"), Decimal("100")),
        NavSnapshot(date(2026, 1, 2), Decimal("110"), Decimal("100")),
        NavSnapshot(date(2026, 1, 3), Decimal("99"), Decimal("100")),
    ]
    rs = daily_returns_from_navs(snaps)
    assert len(rs) == 2
    assert rs[0] == Decimal("0.1")
    # 99/110 - 1 = -0.1
    assert rs[1] == Decimal("99") / Decimal("110") - Decimal("1")


@pytest.mark.parametrize(
    "navs,expected_dd",
    [
        ([Decimal("100")], Decimal("0")),
        ([Decimal("100"), Decimal("50")], Decimal("-50")),
        ([Decimal("100"), Decimal("200"), Decimal("100")], Decimal("-100")),
    ],
)
def test_A18_max_drawdown_parametrize(navs, expected_dd):
    dd, _ = compute_max_drawdown(navs)
    assert dd == expected_dd
