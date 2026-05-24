from app.modules.low_base.scorer import (
    _calculate_institutional_flow_score,
    calculate_low_base_score,
)


def test_strong_low_base_candidate() -> None:
    """Stock with low PE, below MA, good quality = high score."""
    closes = [120.0] * 200 + [float(120 - i * 0.3) for i in range(60)]
    score = calculate_low_base_score(
        symbol="TEST.TW",
        name="Test",
        closes=closes,
        pe=10.0,
        pb=0.8,
        dividend_yield=5.0,
        pe_history=[10, 12, 15, 18, 20, 22, 25, 10],
        industry_avg_pe=18.0,
        roe=0.15,
        debt_ratio=0.3,
        revenue_yoy_growth=8.0,
        eps=3.0,
        health_score=65.0,
        rsi=28.0,
    )
    assert score.total_score > 65
    assert not score.disqualified


def test_overvalued_stock_low_score() -> None:
    """Stock with high PE, above MA = low score."""
    closes = [float(100 + i * 0.5) for i in range(260)]
    score = calculate_low_base_score(
        symbol="HIGH.TW",
        name="High",
        closes=closes,
        pe=35.0,
        pb=5.0,
        dividend_yield=0.5,
        industry_avg_pe=18.0,
        rsi=75.0,
    )
    assert score.total_score < 35


def test_negative_eps_disqualified() -> None:
    score = calculate_low_base_score(
        symbol="LOSS.TW",
        name="Loss",
        closes=[100.0] * 30,
        eps=-2.0,
    )
    assert score.disqualified
    assert "虧損" in score.disqualify_reason


def test_minimal_data() -> None:
    """With only price data, should still produce a score."""
    closes = [float(100 - i * 0.2) for i in range(30)]
    score = calculate_low_base_score(
        symbol="MIN.TW",
        name="Minimal",
        closes=closes,
    )
    assert 0 <= score.total_score <= 100
    assert not score.disqualified


def test_score_components_weighted() -> None:
    closes = [100.0] * 260
    score = calculate_low_base_score(
        symbol="X",
        name="X",
        closes=closes,
        pe=15.0,
        industry_avg_pe=15.0,
        roe=0.10,
        rsi=50.0,
    )
    # With neutral values, score should be around 50
    assert 30 < score.total_score < 70


# ---------------------------------------------------------------------------
# Enhanced scoring (institutional + technical)
# ---------------------------------------------------------------------------


class TestInstitutionalFlowScore:
    def test_all_three_buyers(self) -> None:
        score = _calculate_institutional_flow_score(100.0, 50.0, 30.0)
        # 3 buyers = 100, + foreign bonus 10 -> capped at 100
        assert score == 100.0

    def test_two_buyers_with_foreign(self) -> None:
        # foreign + trust buy, dealer sell
        score = _calculate_institutional_flow_score(100.0, 50.0, -20.0)
        # 2 buyers = 70, + foreign bonus = 80
        assert score == 80.0

    def test_two_buyers_without_foreign(self) -> None:
        # trust + dealer buy, foreign sell
        score = _calculate_institutional_flow_score(-10.0, 50.0, 30.0)
        # 2 buyers = 70, no foreign bonus
        assert score == 70.0

    def test_one_buyer_foreign_only(self) -> None:
        score = _calculate_institutional_flow_score(100.0, -50.0, -30.0)
        # 1 buyer = 40, + foreign bonus = 50
        assert score == 50.0

    def test_no_buyers(self) -> None:
        score = _calculate_institutional_flow_score(-10.0, -50.0, -30.0)
        assert score == 10.0

    def test_none_values_treated_as_non_buyer(self) -> None:
        score = _calculate_institutional_flow_score(None, None, None)
        assert score == 10.0

    def test_zero_is_not_buyer(self) -> None:
        score = _calculate_institutional_flow_score(0.0, 0.0, 0.0)
        assert score == 10.0


class TestEnhancedScoring:
    """Test that institutional+technical params change scoring weights."""

    def _base_closes(self) -> list[float]:
        return [100.0] * 260

    def test_without_enhanced_no_inst_tech_score(self) -> None:
        score = calculate_low_base_score(
            symbol="X",
            name="X",
            closes=self._base_closes(),
        )
        assert score.institutional_technical_score is None
        # Original weights: 40/30/30
        expected = (
            score.valuation_score * 0.4
            + score.price_position_score * 0.3
            + score.quality_score * 0.3
        )
        assert abs(score.total_score - round(expected, 2)) < 0.01

    def test_with_institutional_data_uses_enhanced_weights(self) -> None:
        score = calculate_low_base_score(
            symbol="X",
            name="X",
            closes=self._base_closes(),
            foreign_net_buy_5d=1000.0,
            trust_net_buy_5d=500.0,
            dealer_net_buy_5d=-200.0,
        )
        assert score.institutional_technical_score is not None
        # Enhanced weights: 35/25/25/15
        expected = (
            score.valuation_score * 0.35
            + score.price_position_score * 0.25
            + score.quality_score * 0.25
            + score.institutional_technical_score * 0.15
        )
        assert abs(score.total_score - round(expected, 2)) < 0.01

    def test_with_technical_score_only(self) -> None:
        score = calculate_low_base_score(
            symbol="X",
            name="X",
            closes=self._base_closes(),
            technical_score=80.0,
        )
        assert score.institutional_technical_score is not None
        # Flow defaults to 50 (neutral), technical = 80
        # Combined = 50*0.6 + 80*0.4 = 30 + 32 = 62
        assert abs(score.institutional_technical_score - 62.0) < 0.01

    def test_with_all_enhanced_params(self) -> None:
        score = calculate_low_base_score(
            symbol="X",
            name="X",
            closes=self._base_closes(),
            foreign_net_buy_5d=500.0,
            trust_net_buy_5d=300.0,
            dealer_net_buy_5d=100.0,
            technical_score=90.0,
        )
        assert score.institutional_technical_score is not None
        # All 3 buyers + foreign bonus = 100, tech = 90
        # Combined = 100*0.6 + 90*0.4 = 60 + 36 = 96
        assert abs(score.institutional_technical_score - 96.0) < 0.01

    def test_backward_compatible_no_enhanced_params(self) -> None:
        """Calling without any new params produces identical results."""
        closes = [120.0] * 200 + [float(120 - i * 0.3) for i in range(60)]
        base = calculate_low_base_score(
            symbol="T",
            name="T",
            closes=closes,
            rsi=35.0,
        )
        enhanced = calculate_low_base_score(
            symbol="T",
            name="T",
            closes=closes,
            rsi=35.0,
        )
        assert base.total_score == enhanced.total_score
        assert base.institutional_technical_score is None
        assert enhanced.institutional_technical_score is None

    def test_details_contain_institutional_info(self) -> None:
        score = calculate_low_base_score(
            symbol="X",
            name="X",
            closes=self._base_closes(),
            foreign_net_buy_5d=1000.0,
            trust_net_buy_5d=-500.0,
            dealer_net_buy_5d=200.0,
            technical_score=60.0,
        )
        assert "institutional_flow_score" in score.details
        assert "foreign_net_buy_5d" in score.details
        assert "technical_score" in score.details
        assert "institutional_technical_score" in score.details
