from app.modules.indicators.rsi import RSIIndicator


def test_rsi_name() -> None:
    assert RSIIndicator().name == "RSI"

def test_rsi_basic_calculation() -> None:
    closes = [float(100 + i) for i in range(20)]
    result = RSIIndicator().calculate(closes, period=14)
    rsi_values = result.values["RSI"]
    assert all(v is None for v in rsi_values[:14])
    assert rsi_values[-1] == 100.0

def test_rsi_downtrend() -> None:
    closes = [float(100 - i) for i in range(20)]
    result = RSIIndicator().calculate(closes, period=14)
    assert result.values["RSI"][-1] == 0.0

def test_rsi_mixed() -> None:
    closes = [44.0, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
              46.22, 45.64]
    result = RSIIndicator().calculate(closes, period=14)
    rsi = result.values["RSI"][-1]
    assert rsi is not None
    assert 0 < rsi < 100

def test_rsi_too_short_data() -> None:
    closes = [100.0, 101.0, 102.0]
    result = RSIIndicator().calculate(closes, period=14)
    assert all(v is None for v in result.values["RSI"])

def test_rsi_custom_period() -> None:
    closes = [float(100 + i) for i in range(10)]
    result = RSIIndicator().calculate(closes, period=5)
    assert result.values["RSI"][5] is not None
