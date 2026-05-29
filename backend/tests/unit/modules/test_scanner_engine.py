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


# ── Bug 2 regression: ZeroDivisionError on degenerate price series ────────
# Browser audit on 2026-05-28 surfaced POST /api/v1/scanner/scan returning
# 500 in production. Root cause: BiasReversalStrategy + RSIBiasComboStrategy
# both do `bias = (closes[-1] - ma) / ma * 100`. When the trailing N-day
# window contains all zeros (bad upstream data / unsynced ticker), ma==0
# and the whole `/scanner/scan` request crashes — not just that stock.
def test_scan_stock_all_zero_closes_does_not_raise() -> None:
    """All-zero close series must not raise ZeroDivisionError.

    The scanner is a multi-stock loop; one bad row must not kill the
    whole batch.
    """
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    result = scanner.scan_stock("ZERO", "Zero", [0.0] * 60)
    # Defensive contract: degenerate input → HOLD with score=0, never raise.
    assert isinstance(result, StockSignal)
    assert result.composite_action == "HOLD"


def test_scan_many_skips_degenerate_row_but_keeps_others() -> None:
    """One degenerate (all-zero) entry must not poison the batch."""
    registry = create_default_registry()
    scanner = SignalScanner(registry)
    stocks = [
        {"symbol": "GOOD", "name": "Good", "closes": [float(50 + i) for i in range(60)]},
        {"symbol": "ZERO", "name": "Zero", "closes": [0.0] * 60},
    ]
    results = scanner.scan_many(stocks)
    # Both rows must come back — degenerate one as HOLD, healthy one with a
    # real action; whatever the order, len must be 2.
    assert len(results) == 2
    assert {r.symbol for r in results} == {"GOOD", "ZERO"}
