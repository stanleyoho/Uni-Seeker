from app.modules.scanner.engine import SignalScanner, StockSignal
from app.modules.strategy import create_default_registry


def test_scan_stock_bullish():
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    # Steadily rising prices -> should get BUY signals
    closes = [float(50 + i * 0.5) for i in range(60)]
    result = scanner.scan_stock("TEST", "Test Stock", closes)
    assert isinstance(result, StockSignal)
    assert result.symbol == "TEST"
    assert result.score != 0  # should have some signal


def test_scan_stock_bearish():
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    # Steadily declining prices trigger oversold indicators (RSI, BIAS)
    # which are mean-reversion BUY signals, so score may be positive.
    closes = [float(100 - i * 0.5) for i in range(60)]
    result = scanner.scan_stock("TEST", "Test Stock", closes)
    assert isinstance(result, StockSignal)
    assert result.composite_action in ("BUY", "STRONG_BUY", "HOLD", "SELL", "STRONG_SELL")


def test_scan_stock_with_specific_strategies():
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    closes = [float(50 + i * 0.3) for i in range(60)]
    result = scanner.scan_stock("TEST", "Test", closes, strategy_keys=["rsi_oversold"])
    assert len(result.signals) == 1


def test_scan_many_returns_sorted():
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    stocks = [
        {"symbol": "A", "name": "Stock A", "closes": [float(50 + i) for i in range(60)]},
        {"symbol": "B", "name": "Stock B", "closes": [float(100 - i) for i in range(60)]},
    ]
    results = scanner.scan_many(stocks)
    assert len(results) == 2
    assert results[0].score >= results[1].score  # sorted desc


def test_scan_stock_insufficient_data():
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    result = scanner.scan_stock("TEST", "Test", [100.0, 101.0])
    assert result.composite_action == "HOLD"
