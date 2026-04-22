from app.modules.indicators.macd import MACDIndicator


def test_macd_name() -> None:
    assert MACDIndicator().name == "MACD"

def test_macd_result_keys() -> None:
    closes = [float(100 + i * 0.5) for i in range(40)]
    result = MACDIndicator().calculate(closes, fast=12, slow=26, signal=9)
    assert "MACD" in result.values
    assert "signal" in result.values
    assert "histogram" in result.values
    assert len(result.values["MACD"]) == 40

def test_macd_uptrend_positive() -> None:
    closes = [float(100 + i * 2) for i in range(40)]
    result = MACDIndicator().calculate(closes)
    macd_values = [v for v in result.values["MACD"] if v is not None]
    assert macd_values[-1] > 0

def test_macd_insufficient_data() -> None:
    closes = [100.0] * 10
    result = MACDIndicator().calculate(closes, fast=12, slow=26, signal=9)
    assert all(v is None for v in result.values["MACD"])
