"""Plan 5 T4 — StockSharpDetector divergence logic tests."""

from datetime import date

from app.modules.stock_signals.sharp_detector import (
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
        assert isinstance(edge.reason, str)
        assert len(edge.reason) > 0

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

    def test_confidence_higher_with_divergence_than_without(self):
        """Edge confidence with divergence must exceed edge confidence without."""
        detector_divergence = StockSharpDetector(
            foreign_futures_net=15000.0,
            margin_balance_change=-80.0,  # divergence
        )
        detector_no_divergence = StockSharpDetector(
            foreign_futures_net=15000.0,
            margin_balance_change=80.0,  # both long, no divergence
        )
        edge_div = detector_divergence.get_edge_signal("2330", date(2026, 5, 9))
        edge_no = detector_no_divergence.get_edge_signal("2330", date(2026, 5, 9))
        assert edge_div.confidence > edge_no.confidence

    def test_reason_is_human_readable(self):
        """Reason field should be non-trivial Chinese text mentioning 法人."""
        detector = StockSharpDetector(
            foreign_futures_net=8000.0,
            margin_balance_change=-40.0,  # divergence
        )
        edge = detector.get_edge_signal("0050", date(2026, 5, 9))
        assert len(edge.reason) > 20
        assert "法人" in edge.reason or "divergence" in edge.reason.lower()

    def test_confidence_capped_at_0_9(self):
        """Even with extreme institutional positions, confidence must not exceed 0.9."""
        detector = StockSharpDetector(
            foreign_futures_net=999999.0,
            margin_balance_change=-999.0,  # divergence with extreme magnitude
        )
        edge = detector.get_edge_signal("2330", date(2026, 5, 9))
        assert edge.confidence <= 0.9

    def test_neutral_direction_has_zero_confidence(self):
        """When both sides are at zero, edge must be neutral with zero confidence."""
        detector = StockSharpDetector(
            foreign_futures_net=0.0,
            margin_balance_change=0.0,
        )
        edge = detector.get_edge_signal("2330", date(2026, 5, 9))
        assert edge.direction == "neutral"
        assert edge.confidence == 0.0
