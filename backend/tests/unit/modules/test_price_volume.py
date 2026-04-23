from app.modules.indicators.price_volume import PriceVolumeIndicator


def test_pv_name() -> None:
    assert PriceVolumeIndicator().name == "PV"


def test_volume_ratio() -> None:
    closes = [100.0] * 10
    volumes = [1000] * 5 + [2000] * 5
    result = PriceVolumeIndicator().calculate(
        closes, volumes=volumes, indicator_type="volume_ratio", period=5
    )
    ratios = result.values["volume_ratio"]
    assert ratios[5] is not None
    assert ratios[5] == 2.0  # 2000 / avg(1000*5)


def test_volume_surge() -> None:
    closes = [100.0] * 25
    volumes = [1000] * 20 + [5000, 1000, 1000, 1000, 1000]
    result = PriceVolumeIndicator().calculate(
        closes, volumes=volumes, indicator_type="volume_surge", period=20
    )
    surge = result.values["volume_surge"]
    assert surge[20] is not None
    assert surge[20] == 5.0  # 5000 / 1000


def test_amplitude() -> None:
    closes = [100.0, 102.0, 98.0]
    highs = [105.0, 108.0, 103.0]
    lows = [95.0, 97.0, 93.0]
    result = PriceVolumeIndicator().calculate(
        closes, highs=highs, lows=lows, indicator_type="amplitude"
    )
    amp = result.values["amplitude"]
    assert amp[0] is None
    assert amp[1] is not None
    # (108 - 97) / 100 * 100 = 11.0
    assert amp[1] == 11.0


def test_new_high_low() -> None:
    closes = [float(100 + i) for i in range(25)]  # steadily rising
    result = PriceVolumeIndicator().calculate(
        closes, indicator_type="new_high_low", period=20
    )
    signals = result.values["new_high_low"]
    # Should be new highs since price is always rising
    assert signals[20] == 1


def test_new_low() -> None:
    closes = [float(100 - i) for i in range(25)]  # steadily falling
    result = PriceVolumeIndicator().calculate(
        closes, indicator_type="new_high_low", period=20
    )
    signals = result.values["new_high_low"]
    assert signals[20] == -1


def test_multi_period_change() -> None:
    closes = [float(100 + i) for i in range(250)]
    result = PriceVolumeIndicator().calculate(
        closes, indicator_type="price_change"
    )
    assert "change_5d" in result.values
    assert "change_20d" in result.values
    assert "change_60d" in result.values
    assert "change_120d" in result.values
    assert "change_240d" in result.values
    # 5-day change at index 5: (105-100)/100*100 = 5.0
    assert result.values["change_5d"][5] == 5.0


def test_insufficient_data() -> None:
    closes = [100.0, 101.0]
    result = PriceVolumeIndicator().calculate(
        closes, indicator_type="volume_ratio", volumes=[1000, 1100], period=5
    )
    assert all(v is None for v in result.values["volume_ratio"])
