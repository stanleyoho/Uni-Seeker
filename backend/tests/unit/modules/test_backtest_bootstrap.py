"""Tests for bootstrap confidence intervals (A2 audit item).

Coverage:
* CI math against a known distribution (seeded -> stable, percentiles within
  tolerance of the analytic / large-sample expectation).
* Determinism (same seed -> identical CIs; different seed -> different draws).
* CI ordering invariants (ci_low <= median <= ci_high).
* Edge cases: empty portfolio, single trade, flat equity, configurable K.
"""

from __future__ import annotations

import math

import pytest

from app.modules.backtester.bootstrap import (
    DEFAULT_BOOTSTRAP_SAMPLES,
    BootstrapMetrics,
    MetricCI,
    bootstrap_metrics,
    daily_returns_from_equity,
    trade_pnls_from_portfolio,
)
from app.modules.backtester.portfolio import Portfolio, Trade


def _portfolio_with_equity(equity: list[float]) -> Portfolio:
    p = Portfolio(initial_capital=equity[0] if equity else 100_000)
    p.equity_curve = list(equity)
    return p


def _add_trade(p: Portfolio, action: str, price: float, shares: int = 1) -> None:
    p.trades.append(
        Trade(
            symbol="X",
            action=action,
            date="2026-01-01",
            price=price,
            shares=shares,
            cost=price * shares,
            reason="test",
        )
    )


# --------------------------------------------------------------------------- #
# Sample extraction
# --------------------------------------------------------------------------- #


def test_daily_returns_from_equity_basic() -> None:
    returns = daily_returns_from_equity([100.0, 110.0, 99.0])
    assert returns == pytest.approx([0.10, -0.1])


def test_daily_returns_skips_nonpositive_prior() -> None:
    # A zero prior equity would divide by zero; that step is skipped.
    returns = daily_returns_from_equity([0.0, 50.0, 100.0])
    assert returns == [1.0]  # only 50 -> 100


def test_trade_pnls_fifo_matching() -> None:
    p = Portfolio(initial_capital=100_000)
    _add_trade(p, "BUY", 100.0, shares=2)
    _add_trade(p, "SELL", 120.0, shares=2)  # +40 pnl
    _add_trade(p, "BUY", 50.0, shares=1)
    _add_trade(p, "SELL", 40.0, shares=1)  # -10 pnl
    pnls = trade_pnls_from_portfolio(p)
    assert pnls == [40.0, -10.0]


# --------------------------------------------------------------------------- #
# CI math vs a known distribution
# --------------------------------------------------------------------------- #


def test_win_rate_ci_known_distribution() -> None:
    """A portfolio with exactly 60% winning trades.

    Bootstrapping a Bernoulli(p=0.6) sample of 100 trades, the resampled
    win-rate distribution centres on 60%, and a 90% CI brackets it. With a
    large, balanced sample and K=2000 resamples the median should land very
    close to 60%.
    """
    p = Portfolio(initial_capital=100_000)
    # 60 winners (buy 100 -> sell 110), 40 losers (buy 100 -> sell 90).
    for _ in range(60):
        _add_trade(p, "BUY", 100.0)
        _add_trade(p, "SELL", 110.0)
    for _ in range(40):
        _add_trade(p, "BUY", 100.0)
        _add_trade(p, "SELL", 90.0)

    bs = bootstrap_metrics(p, samples=2000, seed=7)
    assert bs.win_rate is not None
    wr = bs.win_rate
    # Median within 2 pts of the true 60%.
    assert abs(wr.median - 60.0) < 2.0
    # 90% CI brackets the truth and has sensible width for n=100, p=0.6
    # (analytic SE ~ 4.9 pts; 90% CI half-width ~ 8 pts).
    assert wr.ci_low < 60.0 < wr.ci_high
    assert wr.ci_low <= wr.median <= wr.ci_high
    assert 50.0 < wr.ci_low < 60.0
    assert 60.0 < wr.ci_high < 72.0


def test_sharpe_ci_brackets_point_estimate() -> None:
    """Sharpe CI should bracket the full-sample Sharpe for a steady uptrend."""
    # Steady ~1%/day uptrend with mild noise via alternating steps.
    equity = [100.0]
    for i in range(1, 120):
        step = 1.01 if i % 3 else 1.005
        equity.append(equity[-1] * step)
    p = _portfolio_with_equity(equity)

    returns = daily_returns_from_equity(equity)
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    point_sharpe = mean / math.sqrt(var) * math.sqrt(252)

    bs = bootstrap_metrics(p, samples=2000, seed=11)
    assert bs.sharpe_ratio is not None
    s = bs.sharpe_ratio
    assert s.ci_low <= s.median <= s.ci_high
    # Point estimate falls inside the 90% CI.
    assert s.ci_low <= point_sharpe <= s.ci_high


def test_max_drawdown_ci_is_nonpositive() -> None:
    equity = [100.0, 120.0, 90.0, 110.0, 80.0, 130.0]
    p = _portfolio_with_equity(equity)
    bs = bootstrap_metrics(p, samples=1000, seed=3)
    assert bs.max_drawdown is not None
    dd = bs.max_drawdown
    # Drawdowns are <= 0 by construction.
    assert dd.ci_high <= 0.0
    assert dd.ci_low <= dd.median <= dd.ci_high


def test_annualized_return_ci_ordering() -> None:
    equity = [100.0]
    for i in range(1, 80):
        equity.append(equity[-1] * (1.02 if i % 2 else 0.99))
    p = _portfolio_with_equity(equity)
    bs = bootstrap_metrics(p, samples=1500, seed=5)
    assert bs.annualized_return is not None
    ar = bs.annualized_return
    assert ar.ci_low <= ar.median <= ar.ci_high


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_same_seed_is_deterministic() -> None:
    equity = [100.0, 105.0, 103.0, 110.0, 108.0, 115.0, 112.0]
    p1 = _portfolio_with_equity(equity)
    p2 = _portfolio_with_equity(equity)
    a = bootstrap_metrics(p1, samples=500, seed=99)
    b = bootstrap_metrics(p2, samples=500, seed=99)
    assert a == b


def test_different_seed_changes_draws() -> None:
    equity = [100.0, 105.0, 103.0, 110.0, 108.0, 115.0, 112.0]
    p = _portfolio_with_equity(equity)
    a = bootstrap_metrics(p, samples=500, seed=1)
    b = bootstrap_metrics(p, samples=500, seed=2)
    assert a.sharpe_ratio != b.sharpe_ratio


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_empty_portfolio_yields_all_none() -> None:
    p = Portfolio(initial_capital=100_000)  # no equity, no trades
    bs = bootstrap_metrics(p, samples=1000, seed=0)
    assert isinstance(bs, BootstrapMetrics)
    assert bs.sharpe_ratio is None
    assert bs.annualized_return is None
    assert bs.max_drawdown is None
    assert bs.win_rate is None
    assert bs.samples == 1000


def test_single_return_point_no_return_cis() -> None:
    # Only one return observation -> below the 2-point floor.
    p = _portfolio_with_equity([100.0, 110.0])
    bs = bootstrap_metrics(p, samples=1000, seed=0)
    assert bs.sharpe_ratio is None
    assert bs.annualized_return is None
    assert bs.max_drawdown is None


def test_single_trade_win_rate_ci_degenerate() -> None:
    p = Portfolio(initial_capital=100_000)
    _add_trade(p, "BUY", 100.0)
    _add_trade(p, "SELL", 120.0)  # one winning trade
    bs = bootstrap_metrics(p, samples=1000, seed=0)
    assert bs.win_rate is not None
    # Resampling a single winner always yields 100% wins.
    assert bs.win_rate.median == 100.0
    assert bs.win_rate.ci_low == 100.0
    assert bs.win_rate.ci_high == 100.0


def test_flat_equity_zero_sharpe() -> None:
    p = _portfolio_with_equity([100.0] * 30)
    bs = bootstrap_metrics(p, samples=500, seed=0)
    assert bs.sharpe_ratio is not None
    # Zero variance -> Sharpe defined as 0 in every resample.
    assert bs.sharpe_ratio.median == 0.0
    assert bs.sharpe_ratio.ci_low == 0.0
    assert bs.sharpe_ratio.ci_high == 0.0


def test_samples_clamped_to_at_least_one() -> None:
    p = _portfolio_with_equity([100.0, 110.0, 105.0])
    bs = bootstrap_metrics(p, samples=0, seed=0)
    assert bs.samples == 1
    assert bs.sharpe_ratio is not None  # one resample still produces a CI


def test_default_samples_constant() -> None:
    p = _portfolio_with_equity([100.0, 110.0, 105.0, 120.0])
    bs = bootstrap_metrics(p, seed=0)
    assert bs.samples == DEFAULT_BOOTSTRAP_SAMPLES


def test_metric_ci_is_frozen() -> None:
    ci = MetricCI(median=1.0, ci_low=0.5, ci_high=1.5)
    try:
        ci.median = 2.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("MetricCI should be immutable (frozen dataclass)")
