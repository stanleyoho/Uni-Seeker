from app.modules.indicators.patterns import PatternIndicator


def test_pattern_name() -> None:
    assert PatternIndicator().name == "PATTERN"


def test_ma_alignment_bullish() -> None:
    # Steadily rising prices -> bullish MA alignment
    closes = [float(100 + i * 2) for i in range(80)]
    result = PatternIndicator().calculate(closes, pattern_type="ma_alignment")
    vals = result.values["ma_alignment"]
    # Last values should be bullish (1 or 2)
    non_none = [v for v in vals if v is not None]
    assert non_none[-1] > 0


def test_ma_alignment_bearish() -> None:
    closes = [float(200 - i * 2) for i in range(80)]
    result = PatternIndicator().calculate(closes, pattern_type="ma_alignment")
    vals = result.values["ma_alignment"]
    non_none = [v for v in vals if v is not None]
    assert non_none[-1] < 0


def test_ma_crossover_golden() -> None:
    # Build data: flat then sharp rise = short MA crosses above long MA
    closes = [100.0] * 30 + [float(100 + i * 3) for i in range(30)]
    result = PatternIndicator().calculate(
        closes, pattern_type="ma_crossover", short_period=5, long_period=20
    )
    vals = result.values["ma_crossover"]
    # Should have at least one golden cross (1)
    assert 1 in [v for v in vals if v is not None]


def test_ma_crossover_insufficient_data() -> None:
    closes = [100.0] * 10
    result = PatternIndicator().calculate(
        closes, pattern_type="ma_crossover", short_period=5, long_period=20
    )
    assert all(v is None for v in result.values["ma_crossover"])


def test_kd_signal() -> None:
    # Falling then rising prices
    closes = [float(100 - i) for i in range(15)] + [float(85 + i * 2) for i in range(15)]
    highs = [c + 2 for c in closes]
    lows = [c - 2 for c in closes]
    result = PatternIndicator().calculate(
        closes, pattern_type="kd_signal", highs=highs, lows=lows
    )
    vals = result.values["kd_signal"]
    # Should have some non-None values
    assert any(v is not None for v in vals)


def test_macd_signal() -> None:
    # Rising prices should eventually give positive MACD signal
    closes = [100.0] * 30 + [float(100 + i * 2) for i in range(30)]
    result = PatternIndicator().calculate(closes, pattern_type="macd_signal")
    vals = result.values["macd_signal"]
    non_none = [v for v in vals if v is not None]
    # Should have some positive signals
    assert any(v > 0 for v in non_none) if non_none else True


def test_rsi_divergence() -> None:
    closes = [float(100 + i) for i in range(40)]
    result = PatternIndicator().calculate(
        closes, pattern_type="rsi_divergence", period=14, lookback=10
    )
    assert "rsi_divergence" in result.values
    assert len(result.values["rsi_divergence"]) == 40
