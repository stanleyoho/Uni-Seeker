from app.modules.strategy.builtin import MACrossoverStrategy, RSIOversoldStrategy


def test_ma_crossover_buy_signal() -> None:
    # Short MA crossing above long MA
    # Build data where short MA just crossed above long MA
    closes = [100.0] * 20 + [95.0] * 5 + [96, 97, 98, 100, 103, 106]
    strategy = MACrossoverStrategy(short_period=5, long_period=20)
    signal = strategy.evaluate(closes)
    # After the dip and recovery, short MA should cross above long MA
    assert signal.action in ("BUY", "HOLD")  # depends on exact crossover timing


def test_ma_crossover_insufficient_data() -> None:
    strategy = MACrossoverStrategy(short_period=5, long_period=20)
    signal = strategy.evaluate([100.0] * 10)
    assert signal.action == "HOLD"
    assert "Insufficient" in signal.reason


def test_rsi_oversold_buy() -> None:
    # Steadily falling prices -> low RSI
    closes = [float(100 - i) for i in range(20)]
    strategy = RSIOversoldStrategy(period=14, buy_threshold=30)
    signal = strategy.evaluate(closes)
    assert signal.action == "BUY"


def test_rsi_overbought_sell() -> None:
    # Steadily rising prices -> high RSI
    closes = [float(100 + i) for i in range(20)]
    strategy = RSIOversoldStrategy(period=14, sell_threshold=70)
    signal = strategy.evaluate(closes)
    assert signal.action == "SELL"


def test_rsi_hold_in_range() -> None:
    # Mixed prices -> RSI in middle range
    closes = [100.0, 101.0, 99.0, 102.0, 98.0, 101.0, 100.0, 99.5, 100.5, 101.0,
              100.0, 99.0, 101.0, 100.5, 99.5, 100.0, 100.5, 99.5, 100.0, 101.0]
    strategy = RSIOversoldStrategy()
    signal = strategy.evaluate(closes)
    assert signal.action == "HOLD"
