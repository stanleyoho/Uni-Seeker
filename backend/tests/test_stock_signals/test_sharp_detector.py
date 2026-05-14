"""Plan 5 T4 — StockSharpDetector divergence logic tests."""
from datetime import date

import pytest

from app.modules.stock_signals.sharp_detector import (
    EdgeSignal,
    StockSharpDetector,
    StockSharpSignal,
)


class TestStockSharpDetector:
    """4 institutional × retail combinations + 3 edge-signal scenarios."""

    def setup_method(self):
        self.detector = StockSharpDetector()

    def test_institutional_long_retail_bullish_no_divergence(self):
        signal = self.detector.detect_divergence(
            foreign_futures_net=5000.0,
            margin_balance_change=20.0,
        )
        assert isinstance(signal, StockSharpSignal)
        assert signal.divergence_detected is False
        assert signal.institutional_direction == "long"
        assert signal.retail_direction == "long"

    def test_institutional_long_retail_bearish_divergence(self):
        signal = self.detector.detect_divergence(
            foreign_futures_net=8000.0,
            margin_balance_change=-30.0,
        )
        assert signal.divergence_detected is True
        assert signal.institutional_direction == "long"
        assert signal.retail_direction == "short"

    def test_institutional_short_retail_bullish_divergence(self):
        signal = self.detector.detect_divergence(
            foreign_futures_net=-6000.0,
            margin_balance_change=15.0,
        )
        assert signal.divergence_detected is True
        assert signal.institutional_direction == "short"
        assert signal.retail_direction == "long"

    def test_institutional_short_retail_bearish_no_divergence(self):
        signal = self.detector.detect_divergence(
            foreign_futures_net=-4000.0,
            margin_balance_change=-25.0,
        )
        assert signal.divergence_detected is False
        assert signal.institutional_direction == "short"
        assert signal.retail_direction == "short"

    def test_near_zero_both_neutral(self):
        signal = self.detector.detect_divergence(
            foreign_futures_net=50.0,
            margin_balance_change=0.5,
        )
        assert signal.institutional_direction == "neutral"
        assert signal.retail_direction == "neutral"
        assert signal.divergence_detected is False

    def test_get_edge_signal_long_on_divergence(self):
        detector = StockSharpDetector(
            foreign_futures_net=10000.0,
            margin_balance_change=-50.0,
        )
        edge = detector.get_edge_signal(stock_id="2330", date=date(2026, 5, 9))
        assert edge.direction == "long"
        assert edge.divergence_detected is True
        assert 0.0 <= edge.confidence <= 1.0
        assert isinstance(edge.reason, str) and len(edge.reason) > 0

    def test_get_edge_signal_short_on_divergence(self):
        detector = StockSharpDetector(
            foreign_futures_net=-10000.0,
            margin_balance_change=50.0,
        )
        edge = detector.get_edge_signal(stock_id="2330", date=date(2026, 5, 9))
        assert edge.direction == "short"

    def test_get_edge_signal_neutral_no_divergence(self):
        detector = StockSharpDetector(
            foreign_futures_net=3000.0,
            margin_balance_change=10.0,
        )
        edge = detector.get_edge_signal(stock_id="2330", date=date(2026, 5, 9))
        assert edge.direction == "neutral"
        assert edge.divergence_detected is False
