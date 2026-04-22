from app.modules.indicators.moving_average import MovingAverageIndicator


def test_ma_name() -> None:
    assert MovingAverageIndicator().name == "MA"

def test_ma_sma_basic() -> None:
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = MovingAverageIndicator().calculate(closes, period=3, ma_type="SMA")
    sma = result.values["MA"]
    assert sma[0] is None
    assert sma[1] is None
    assert sma[2] == 20.0
    assert sma[3] == 30.0
    assert sma[4] == 40.0

def test_ma_ema_basic() -> None:
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = MovingAverageIndicator().calculate(closes, period=3, ma_type="EMA")
    ema = result.values["MA"]
    assert ema[0] is None
    assert ema[1] is None
    assert ema[2] == 20.0
    assert ema[3] is not None
    assert ema[3] > 20.0

def test_ma_default_periods() -> None:
    closes = [float(100 + i) for i in range(250)]
    result = MovingAverageIndicator().calculate(closes, period=5)
    assert len(result.values["MA"]) == 250

def test_ma_insufficient_data() -> None:
    closes = [100.0, 101.0]
    result = MovingAverageIndicator().calculate(closes, period=5)
    assert all(v is None for v in result.values["MA"])
