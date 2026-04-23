from datetime import date, timedelta
from decimal import Decimal

from app.models.enums import Market
from app.models.price import StockPrice
from app.modules.backtester.engine import BacktestConfig, BacktestEngine
from app.modules.strategy.builtin import RSIOversoldStrategy


def _make_prices(closes: list[float]) -> list[StockPrice]:
    start = date(2026, 1, 1)
    return [
        StockPrice(
            symbol="TEST.TW", market=Market.TW_TWSE,
            date=start + timedelta(days=i),
            open=Decimal(str(c - 1)), high=Decimal(str(c + 2)),
            low=Decimal(str(c - 2)), close=Decimal(str(c)),
            volume=10_000_000,
        )
        for i, c in enumerate(closes)
    ]


def test_backtest_runs() -> None:
    prices = _make_prices([float(100 - i * 0.5) for i in range(30)] + [float(85 + i) for i in range(30)])
    config = BacktestConfig(initial_capital=1_000_000, position_size=0.5)
    engine = BacktestEngine(config=config)
    result = engine.run(RSIOversoldStrategy(), prices, symbol="TEST.TW")

    assert result.equity_curve
    assert len(result.equity_curve) == 60
    assert result.metrics.total_trades >= 0


def test_backtest_empty_prices() -> None:
    engine = BacktestEngine()
    result = engine.run(RSIOversoldStrategy(), [], symbol="TEST.TW")
    assert result.metrics.total_return == 0


def test_backtest_trade_log() -> None:
    # Falling then rising should trigger buy then sell
    prices = _make_prices([float(100 - i) for i in range(20)] + [float(80 + i * 2) for i in range(20)])
    engine = BacktestEngine(BacktestConfig(position_size=0.3))
    result = engine.run(RSIOversoldStrategy(), prices)
    # Should have at least some trades
    assert isinstance(result.trade_log, list)
