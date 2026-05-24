"""Cross-repo API contract test: backtesting_core (consumed by Uni-Seeker).

Uni-Seeker's ``tests/unit/modules/test_backtesting_core_integration.py``
consumes the following surface of upstream ``backtesting_core`` (monorepo
path-dep ``adaptive-alpha-engine/packages/backtesting_core``):

  - ``from backtesting_core import (
        StockMetrics, StockMetricsReport, Trade, WalkForwardValidator)``
  - ``Trade(buy_date=..., sell_date=..., buy_price=..., sell_price=..., shares=...)``
  - ``WalkForwardValidator(n_splits=..., test_size=..., purge_gap=..., embargo=...)``
  - ``validator.split(df)`` returns iterable of (train_idx, test_idx)
  - ``StockMetrics()`` constructed with no required args
  - ``StockMetrics().compute(trades, equity_curve)`` returns ``StockMetricsReport``
  - ``StockMetricsReport`` exposes ``.total_trades``, ``.win_rate``,
    ``.max_drawdown``, ``.sharpe_ratio``, ``.sortino_ratio``, ``.net_return``,
    ``.net_return_after_cost``

This test pins those public symbols + keyword arguments + report attributes.
Surfaces *not* invoked by Uni-Seeker (``GameMetrics``, ``GamePrediction`` —
those are pinned by sports-prophet's parallel contract test) are intentionally
NOT pinned here. Each downstream repo pins only what it consumes.

If upstream drifts (rename a kwarg, reorder a positional, drop a field), this
test fails fast at CI time rather than at runtime inside the integration test.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest


@pytest.fixture(scope="module")
def bc():
    """Import upstream lazily; skip if path-dep is not installed."""
    return pytest.importorskip("backtesting_core")


# ── public symbol presence ──────────────────────────────────────────────────


def test_top_level_exports_used_by_uniseeker(bc):
    """Uni-Seeker does ``from backtesting_core import (StockMetrics,
    StockMetricsReport, Trade, WalkForwardValidator)``."""
    expected = {"StockMetrics", "StockMetricsReport", "Trade", "WalkForwardValidator"}
    missing = expected - set(dir(bc))
    assert not missing, f"missing top-level exports: {missing}"


# ── signature pinning ───────────────────────────────────────────────────────


def test_WalkForwardValidator_init_kwargs():
    """Uni-Seeker calls
    ``WalkForwardValidator(n_splits=4, test_size=30, purge_gap=5, embargo=5)``."""
    from backtesting_core import WalkForwardValidator

    params = set(inspect.signature(WalkForwardValidator.__init__).parameters.keys())
    required = {"n_splits", "test_size", "purge_gap", "embargo"}
    missing = required - params
    assert not missing, f"WalkForwardValidator.__init__ missing kwargs: {missing}; got {params}"


def test_WalkForwardValidator_split_signature():
    """Uni-Seeker calls ``list(v.split(df))`` and unpacks ``(train_idx, test_idx)``."""
    from backtesting_core import WalkForwardValidator

    params = list(inspect.signature(WalkForwardValidator.split).parameters.keys())
    assert params[0] == "self", f"got {params}"
    # At least one non-self positional argument (the dataframe).
    assert len(params) >= 2, f"split() must accept a dataframe arg; got {params}"


def test_StockMetrics_init_has_no_required_kwargs():
    """Uni-Seeker calls ``StockMetrics()`` with no args."""
    from backtesting_core import StockMetrics

    sig = inspect.signature(StockMetrics.__init__)
    # All non-self params must have defaults.
    required_no_default = [
        name
        for name, p in sig.parameters.items()
        if name != "self" and p.default is inspect.Parameter.empty
    ]
    assert not required_no_default, (
        f"StockMetrics() must be callable with no args; "
        f"unexpected required params: {required_no_default}"
    )


def test_StockMetrics_compute_signature():
    """Uni-Seeker calls ``sm.compute(trades, equity)``."""
    from backtesting_core import StockMetrics

    params = list(inspect.signature(StockMetrics.compute).parameters.keys())
    assert params[0] == "self"
    # Need at least two non-self positional arguments (trades + equity_curve).
    assert len(params) >= 3, f"compute() must accept (trades, equity); got {params}"


# ── dataclass field presence ────────────────────────────────────────────────


def test_Trade_fields():
    """Uni-Seeker constructs
    ``Trade(buy_date, sell_date, buy_price, sell_price, shares)``."""
    from backtesting_core import Trade

    field_names = {f.name for f in dataclasses.fields(Trade)}
    for required in ("buy_date", "sell_date", "buy_price", "sell_price", "shares"):
        assert required in field_names, f"Trade.{required} missing"


def test_StockMetricsReport_fields():
    """Uni-Seeker reads ``report.total_trades``, ``.win_rate``, ``.max_drawdown``.

    Also pins fields surfaced by the package's documented unit convention
    (``sharpe_ratio``, ``sortino_ratio``, ``net_return``,
    ``net_return_after_cost``) so reporting layers downstream stay aligned.
    """
    from backtesting_core import StockMetricsReport

    field_names = {f.name for f in dataclasses.fields(StockMetricsReport)}
    for required in (
        "total_trades",
        "win_rate",
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "net_return",
        "net_return_after_cost",
    ):
        assert required in field_names, f"StockMetricsReport.{required} missing"
