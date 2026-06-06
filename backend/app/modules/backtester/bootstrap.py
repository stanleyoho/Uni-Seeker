"""Bootstrap confidence intervals for backtest metrics.

Why this module exists
======================
A single backtest produces *one* number per metric (Sharpe = 1.2,
win-rate = 55%). That point estimate hides how much of the result is luck:
re-run the same strategy on a slightly different sample of the same return
distribution and the Sharpe might land at 0.7 or 1.8. The A2 audit flagged
that the backtester reports point estimates with no notion of sampling
uncertainty.

The fix is the *bootstrap* (Efron, 1979): treat the realised series as the
population, resample it with replacement ``K`` times, recompute the metric
on each resample, and read the empirical distribution. The 5th/95th
percentiles of that distribution form a 90% confidence interval. pybroker
ships this as ``bootstrap_confidence_intervals``; we implement the same
technique in ~100 lines of numpy rather than taking on pybroker's heavy,
opinionated framework as a dependency.

What gets a CI and from which series
====================================
Two underlying samples are resampled with replacement:

* **Daily returns** (the per-period equity-curve returns) drive the
  *return-distribution* metrics:

  - ``sharpe_ratio``      — ``mean / std * sqrt(trading_days)`` per resample
  - ``annualized_return`` — compound the resampled returns over the original
    horizon, then annualise (CAGR, in percent)
  - ``max_drawdown``      — rebuild an equity path from the resampled returns
    and measure peak-to-trough (percent, negative)

* **Per-trade PnL** drives the *trade-outcome* metric:

  - ``win_rate`` — fraction of resampled closed trades with PnL > 0 (percent)

Determinism
===========
All randomness flows through a single ``numpy.random.default_rng(seed)``.
With a fixed ``seed`` the CIs are byte-for-byte reproducible, which is what
makes the math testable against a known distribution.

Edge cases
==========
* Fewer than 2 daily returns -> no return-distribution CIs (the metric is
  undefined or degenerate on a single point).
* Zero closed trades -> no win-rate CI.
In both cases the corresponding ``MetricCI`` is omitted (``None``) rather
than fabricated, so callers never present a CI that was not actually
estimated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.modules.backtester.portfolio import Portfolio

# -- Constants ----------------------------------------------------------------

DEFAULT_BOOTSTRAP_SAMPLES = 1000
"""Default number of resamples (K). ~1000 is the conventional floor for
stable 5th/95th percentile estimates while staying cheap (<10ms for a
multi-year daily series)."""

DEFAULT_BOOTSTRAP_SEED = 42
"""Fixed RNG seed so results are reproducible and tests are stable."""

_CI_LOW_PCT = 5.0
_CI_HIGH_PCT = 95.0
_MIN_RETURNS_FOR_CI = 2
_DEFAULT_TRADING_DAYS = 252


# -- Result types -------------------------------------------------------------


@dataclass(frozen=True)
class MetricCI:
    """A bootstrap confidence interval for one metric.

    ``median`` is the 50th percentile of the resampled metric distribution
    (a robust central estimate); ``ci_low`` / ``ci_high`` are the 5th / 95th
    percentiles, i.e. a 90% confidence interval.
    """

    median: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class BootstrapMetrics:
    """Confidence intervals for the backtest's key metrics.

    Any field may be ``None`` when its underlying sample is too small to
    bootstrap (see module docstring, "Edge cases").
    """

    samples: int
    seed: int
    annualized_return: MetricCI | None = None
    sharpe_ratio: MetricCI | None = None
    max_drawdown: MetricCI | None = None
    win_rate: MetricCI | None = None


# -- Sample extraction --------------------------------------------------------


def daily_returns_from_equity(equity: list[float]) -> list[float]:
    """Per-period simple returns from an equity curve.

    Mirrors the daily-return derivation in ``metrics.calculate_metrics`` so
    the bootstrapped Sharpe is consistent with the point estimate: skip any
    step whose prior equity is non-positive (division guard).
    """
    return [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]


def trade_pnls_from_portfolio(portfolio: Portfolio) -> list[float]:
    """Realised PnL per closed (matched BUY->SELL) trade.

    Uses the same FIFO matching as ``metrics.calculate_metrics`` so the
    bootstrapped win-rate is consistent with the reported point estimate.
    """
    buy_map: dict[str, list[float]] = {}
    pnls: list[float] = []
    for t in portfolio.trades:
        if t.action == "BUY":
            buy_map.setdefault(t.symbol, []).append(t.price)
        elif t.action == "SELL" and buy_map.get(t.symbol):
            buy_price = buy_map[t.symbol].pop(0)
            pnls.append((t.price - buy_price) * t.shares)
    return pnls


# -- Per-resample metric kernels ---------------------------------------------


def _sharpe(returns: np.ndarray, trading_days: int) -> float:
    std = float(returns.std())
    if std <= 0:
        return 0.0
    return float(returns.mean()) / std * math.sqrt(trading_days)


def _annualized_return_pct(returns: np.ndarray, trading_days: int) -> float:
    """CAGR (percent) from a sequence of simple returns.

    Compounds ``(1 + r)`` over the sample then annualises by the sample's
    implied year count (``len / trading_days``). Guards against a fully
    wiped-out path (cumulative growth <= 0 -> -100%).
    """
    growth = float(np.prod(1.0 + returns))
    n = returns.shape[0]
    years = n / trading_days
    if years <= 0:
        return 0.0
    if growth <= 0:
        return -100.0
    return (float(growth ** (1.0 / years)) - 1.0) * 100.0


def _max_drawdown_pct(returns: np.ndarray) -> float:
    """Worst peak-to-trough drawdown (percent, <= 0) of the implied equity path."""
    equity = np.cumprod(1.0 + returns)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = (equity - running_peak) / running_peak
    return float(drawdowns.min()) * 100.0


def _percentiles(values: np.ndarray) -> MetricCI:
    low, median, high = np.percentile(values, [_CI_LOW_PCT, 50.0, _CI_HIGH_PCT])
    return MetricCI(
        median=round(float(median), 4),
        ci_low=round(float(low), 4),
        ci_high=round(float(high), 4),
    )


# -- Public API ---------------------------------------------------------------


def bootstrap_metrics(
    portfolio: Portfolio,
    *,
    samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    trading_days: int = _DEFAULT_TRADING_DAYS,
) -> BootstrapMetrics:
    """Compute bootstrap confidence intervals for a finished backtest.

    Parameters
    ----------
    portfolio:
        The completed ``Portfolio`` (equity curve + trade log).
    samples:
        Number of bootstrap resamples ``K`` (default ``1000``). Values below
        ``1`` are clamped to ``1``.
    seed:
        RNG seed for reproducibility (default ``42``).
    trading_days:
        Periods per year used to annualise Sharpe / CAGR (default ``252``).

    Returns
    -------
    BootstrapMetrics with a ``MetricCI`` per metric, or ``None`` for any
    metric whose underlying sample is too small to bootstrap.
    """
    k = max(1, samples)
    rng = np.random.default_rng(seed)

    returns = np.asarray(daily_returns_from_equity(portfolio.equity_curve), dtype=float)
    pnls = np.asarray(trade_pnls_from_portfolio(portfolio), dtype=float)

    annualized_ci: MetricCI | None = None
    sharpe_ci: MetricCI | None = None
    max_dd_ci: MetricCI | None = None
    win_rate_ci: MetricCI | None = None

    # --- Return-distribution metrics (resample daily returns) ---
    if returns.shape[0] >= _MIN_RETURNS_FOR_CI:
        n = returns.shape[0]
        # One (k, n) matrix of resample indices: each row is an IID draw with
        # replacement of the original return series.
        idx = rng.integers(0, n, size=(k, n))
        resampled = returns[idx]  # shape (k, n)

        sharpe_vals = np.empty(k, dtype=float)
        annual_vals = np.empty(k, dtype=float)
        max_dd_vals = np.empty(k, dtype=float)
        for i in range(k):
            row = resampled[i]
            sharpe_vals[i] = _sharpe(row, trading_days)
            annual_vals[i] = _annualized_return_pct(row, trading_days)
            max_dd_vals[i] = _max_drawdown_pct(row)

        sharpe_ci = _percentiles(sharpe_vals)
        annualized_ci = _percentiles(annual_vals)
        max_dd_ci = _percentiles(max_dd_vals)

    # --- Trade-outcome metric (resample per-trade PnL) ---
    if pnls.shape[0] >= 1:
        m = pnls.shape[0]
        idx = rng.integers(0, m, size=(k, m))
        resampled_pnls = pnls[idx]  # shape (k, m)
        # Win-rate per resample = fraction of trades with PnL > 0, in percent.
        win_rate_vals = (resampled_pnls > 0).mean(axis=1) * 100.0
        win_rate_ci = _percentiles(win_rate_vals)

    return BootstrapMetrics(
        samples=k,
        seed=seed,
        annualized_return=annualized_ci,
        sharpe_ratio=sharpe_ci,
        max_drawdown=max_dd_ci,
        win_rate=win_rate_ci,
    )


__all__ = [
    "DEFAULT_BOOTSTRAP_SAMPLES",
    "DEFAULT_BOOTSTRAP_SEED",
    "BootstrapMetrics",
    "MetricCI",
    "bootstrap_metrics",
    "daily_returns_from_equity",
    "trade_pnls_from_portfolio",
]
