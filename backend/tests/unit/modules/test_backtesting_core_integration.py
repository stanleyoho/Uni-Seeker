"""Integration test: verify backtesting_core is importable and usable inside Uni-Seeker."""
from __future__ import annotations

from datetime import date

import pytest
from backtesting_core import (
    StockMetrics,
    StockMetricsReport,
    Trade,
    WalkForwardValidator,
)


def test_stock_metrics_importable_in_uniseeker() -> None:
    """backtesting_core must be importable from Uni-Seeker's test environment."""
    assert StockMetrics is not None
    assert WalkForwardValidator is not None


def test_walk_forward_validator_produces_splits() -> None:
    """WalkForwardValidator works with 200-row dataset inside Uni-Seeker."""
    import numpy as np
    import pandas as pd

    df = pd.DataFrame({"close": np.linspace(100, 200, 200)})
    v = WalkForwardValidator(n_splits=4, test_size=30, purge_gap=5, embargo=5)
    splits = list(v.split(df))
    assert len(splits) == 4
    for train_idx, test_idx in splits:
        assert len(test_idx) == 30
        assert train_idx.max() < test_idx.min()


def test_stock_metrics_compute_returns_report() -> None:
    """StockMetrics.compute() returns a StockMetricsReport instance."""
    trades = [
        Trade(
            buy_date=date(2024, 1, 2),
            sell_date=date(2024, 1, 12),
            buy_price=100.0,
            sell_price=110.0,
            shares=1000,
        )
    ]
    equity = [1_000_000.0 + i * 1_000 for i in range(120)]
    sm = StockMetrics()
    report = sm.compute(trades, equity)
    assert isinstance(report, StockMetricsReport)
    assert report.total_trades == 1
    assert report.win_rate == pytest.approx(1.0)
    assert report.max_drawdown <= 0.0
