from app.modules.indicators.volume import VolumeIndicator


def test_volume_name() -> None:
    assert VolumeIndicator().name == "VOL"

def test_obv_basic() -> None:
    closes = [10.0, 11.0, 10.5, 11.5, 12.0]
    volumes = [1000, 1500, 1200, 1800, 2000]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="OBV")
    obv = result.values["OBV"]
    assert obv[0] == 1000
    assert obv[1] == 2500
    assert obv[2] == 1300
    assert obv[3] == 3100
    assert obv[4] == 5100

def test_volume_ma() -> None:
    closes = [100.0] * 10
    volumes = [1000 * (i + 1) for i in range(10)]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="VMA", period=5)
    vma = result.values["VMA"]
    assert vma[3] is None
    assert vma[4] == sum(volumes[:5]) / 5

def test_volume_ratio() -> None:
    closes = [100.0] * 10
    volumes = [1000] * 9 + [2000]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="VMA", period=5)
    vma = result.values["VMA"]
    assert vma[-1] is not None
    assert vma[-1] > vma[-2]
