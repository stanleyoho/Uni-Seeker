from app.modules.strategy.base import Signal, Strategy
from app.modules.strategy.builtin import MACrossoverStrategy, RSIOversoldStrategy


def test_ma_crossover_is_strategy() -> None:
    assert isinstance(MACrossoverStrategy(), Strategy)

def test_rsi_oversold_is_strategy() -> None:
    assert isinstance(RSIOversoldStrategy(), Strategy)

def test_signal_creation() -> None:
    s = Signal(action="BUY", symbol="2330.TW", reason="test")
    assert s.action == "BUY"
    assert s.strength == 1.0
