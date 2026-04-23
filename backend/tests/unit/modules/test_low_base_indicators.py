from app.modules.low_base.indicators import (
    calculate_pe_percentile,
    calculate_ma_deviation,
    calculate_peg,
)


def test_pe_percentile_low() -> None:
    # PE of 10 in range [8, 10, 15, 20, 25, 30]
    history = [8.0, 15.0, 20.0, 25.0, 30.0, 10.0]
    result = calculate_pe_percentile(history)
    assert result is not None
    assert result.percentile < 0.5  # bottom half
    assert result.current_pe == 10.0


def test_pe_percentile_high() -> None:
    history = [8.0, 10.0, 15.0, 20.0, 30.0]
    result = calculate_pe_percentile(history)
    assert result is not None
    assert result.percentile == 1.0  # highest


def test_pe_percentile_insufficient() -> None:
    assert calculate_pe_percentile([10.0, 12.0]) is None


def test_ma_deviation_below() -> None:
    closes = [100.0] * 240 + [80.0]
    result = calculate_ma_deviation(closes, 240)
    assert result is not None
    assert result.deviation_pct < 0
    assert abs(result.deviation_pct - (-20.0)) < 1


def test_ma_deviation_above() -> None:
    closes = [100.0] * 240 + [120.0]
    result = calculate_ma_deviation(closes, 240)
    assert result is not None
    assert result.deviation_pct > 0


def test_ma_deviation_insufficient() -> None:
    assert calculate_ma_deviation([100.0] * 10, 240) is None


def test_peg_undervalued() -> None:
    result = calculate_peg(pe=10.0, earnings_growth_pct=15.0)
    assert result is not None
    assert result.peg < 1.0  # undervalued


def test_peg_overvalued() -> None:
    result = calculate_peg(pe=30.0, earnings_growth_pct=5.0)
    assert result is not None
    assert result.peg > 1.0


def test_peg_negative_growth() -> None:
    assert calculate_peg(pe=10.0, earnings_growth_pct=-5.0) is None
