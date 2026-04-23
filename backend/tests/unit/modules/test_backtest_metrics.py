from app.modules.backtester.metrics import calculate_metrics
from app.modules.backtester.portfolio import Portfolio


def test_positive_return() -> None:
    p = Portfolio(initial_capital=100_000)
    p.equity_curve = [100_000, 101_000, 102_000, 103_000, 110_000]
    metrics = calculate_metrics(p)
    assert metrics.total_return > 0


def test_negative_return() -> None:
    p = Portfolio(initial_capital=100_000)
    p.equity_curve = [100_000, 99_000, 98_000, 95_000]
    metrics = calculate_metrics(p)
    assert metrics.total_return < 0


def test_max_drawdown() -> None:
    p = Portfolio(initial_capital=100_000)
    p.equity_curve = [100_000, 110_000, 90_000, 95_000]
    metrics = calculate_metrics(p)
    # From 110k to 90k = -18.18%
    assert metrics.max_drawdown < -15


def test_empty_equity() -> None:
    p = Portfolio(initial_capital=100_000)
    metrics = calculate_metrics(p)
    assert metrics.total_return == 0
    assert metrics.sharpe_ratio == 0
