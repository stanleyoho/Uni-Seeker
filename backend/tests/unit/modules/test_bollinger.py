from app.modules.indicators.bollinger import BollingerBandsIndicator


def test_bb_name() -> None:
    assert BollingerBandsIndicator().name == "BB"

def test_bb_result_keys() -> None:
    closes = [float(100 + i) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20, num_std=2)
    assert "upper" in result.values
    assert "middle" in result.values
    assert "lower" in result.values

def test_bb_middle_is_sma() -> None:
    closes = [float(100 + i) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20)
    sma_20 = sum(closes[:20]) / 20
    assert result.values["middle"][19] == round(sma_20, 4)

def test_bb_upper_above_middle_above_lower() -> None:
    closes = [float(100 + i % 10) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20)
    for i in range(25):
        u = result.values["upper"][i]
        m = result.values["middle"][i]
        lo = result.values["lower"][i]
        if u is not None and m is not None and lo is not None:
            assert u > m > lo

def test_bb_insufficient_data() -> None:
    closes = [100.0] * 5
    result = BollingerBandsIndicator().calculate(closes, period=20)
    assert all(v is None for v in result.values["upper"])
