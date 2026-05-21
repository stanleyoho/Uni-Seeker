"""Plan 5 T5 — stock_signals package public API smoke test."""


def test_stock_signals_exports_detector():
    """The detector class should be re-exported at package level."""
    from app.modules.stock_signals import StockSharpDetector
    assert StockSharpDetector is not None


def test_stock_signals_exports_signal_dataclass():
    """The StockSharpSignal dataclass should be re-exported."""
    from app.modules.stock_signals import StockSharpSignal
    assert StockSharpSignal is not None


def test_stock_signals_exports_edge_dataclass():
    """The EdgeSignal dataclass should be re-exported."""
    from app.modules.stock_signals import EdgeSignal
    assert EdgeSignal is not None


def test_stock_signals_all_lists_public_api():
    """__all__ should declare the public symbols so callers can rely on it."""
    import app.modules.stock_signals as m
    assert hasattr(m, "__all__")
    assert "StockSharpDetector" in m.__all__
    assert "StockSharpSignal" in m.__all__
    assert "EdgeSignal" in m.__all__
