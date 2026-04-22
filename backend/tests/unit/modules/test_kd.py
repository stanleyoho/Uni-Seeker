from app.modules.indicators.kd import KDIndicator


def test_kd_name() -> None:
    assert KDIndicator().name == "KD"

def test_kd_result_keys() -> None:
    highs = [float(110 + i) for i in range(20)]
    lows = [float(90 + i) for i in range(20)]
    closes = [float(100 + i) for i in range(20)]
    result = KDIndicator().calculate(
        closes, highs=highs, lows=lows, k_period=9, k_smooth=3, d_smooth=3,
    )
    assert "K" in result.values
    assert "D" in result.values
    assert len(result.values["K"]) == 20

def test_kd_uptrend_high_values() -> None:
    highs = [float(100 + i * 2) for i in range(20)]
    lows = [float(99 + i * 2) for i in range(20)]
    closes = [float(100 + i * 2) for i in range(20)]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows)
    k_values = [v for v in result.values["K"] if v is not None]
    assert k_values[-1] > 50

def test_kd_insufficient_data() -> None:
    closes = [100.0, 101.0, 102.0]
    highs = [105.0, 106.0, 107.0]
    lows = [95.0, 96.0, 97.0]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows, k_period=9)
    assert all(v is None for v in result.values["K"])

def test_kd_values_between_0_and_100() -> None:
    highs = [float(110 + i % 5) for i in range(30)]
    lows = [float(90 + i % 5) for i in range(30)]
    closes = [float(100 + i % 5) for i in range(30)]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows)
    for v in result.values["K"]:
        if v is not None:
            assert 0 <= v <= 100
    for v in result.values["D"]:
        if v is not None:
            assert 0 <= v <= 100
