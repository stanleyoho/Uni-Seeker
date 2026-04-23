from app.modules.low_base.scorer import calculate_low_base_score


def test_strong_low_base_candidate() -> None:
    """Stock with low PE, below MA, good quality = high score."""
    closes = [120.0] * 200 + [float(120 - i * 0.3) for i in range(60)]
    score = calculate_low_base_score(
        symbol="TEST.TW", name="Test",
        closes=closes,
        pe=10.0, pb=0.8, dividend_yield=5.0,
        pe_history=[10, 12, 15, 18, 20, 22, 25, 10],
        industry_avg_pe=18.0,
        roe=0.15, debt_ratio=0.3,
        revenue_yoy_growth=8.0, eps=3.0,
        health_score=65.0, rsi=28.0,
    )
    assert score.total_score > 65
    assert not score.disqualified


def test_overvalued_stock_low_score() -> None:
    """Stock with high PE, above MA = low score."""
    closes = [float(100 + i * 0.5) for i in range(260)]
    score = calculate_low_base_score(
        symbol="HIGH.TW", name="High",
        closes=closes,
        pe=35.0, pb=5.0, dividend_yield=0.5,
        industry_avg_pe=18.0,
        rsi=75.0,
    )
    assert score.total_score < 35


def test_negative_eps_disqualified() -> None:
    score = calculate_low_base_score(
        symbol="LOSS.TW", name="Loss",
        closes=[100.0] * 30,
        eps=-2.0,
    )
    assert score.disqualified
    assert "虧損" in score.disqualify_reason


def test_minimal_data() -> None:
    """With only price data, should still produce a score."""
    closes = [float(100 - i * 0.2) for i in range(30)]
    score = calculate_low_base_score(
        symbol="MIN.TW", name="Minimal",
        closes=closes,
    )
    assert 0 <= score.total_score <= 100
    assert not score.disqualified


def test_score_components_weighted() -> None:
    closes = [100.0] * 260
    score = calculate_low_base_score(
        symbol="X", name="X", closes=closes,
        pe=15.0, industry_avg_pe=15.0,
        roe=0.10, rsi=50.0,
    )
    # With neutral values, score should be around 50
    assert 30 < score.total_score < 70
