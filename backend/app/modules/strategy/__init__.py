from app.modules.strategy.base import Signal, Strategy, StrategyConfig
from app.modules.strategy.builtin import (
    BiasReversalStrategy,
    BollingerBounceStrategy,
    MACDCrossoverStrategy,
    MACrossoverStrategy,
    RSIBiasComboStrategy,
    RSIOversoldStrategy,
)
from app.modules.strategy.composite import CompositeStrategy
from app.modules.strategy.registry import StrategyRegistry


def create_default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register("ma_crossover", MACrossoverStrategy)
    registry.register("rsi_oversold", RSIOversoldStrategy)
    registry.register("macd_crossover", MACDCrossoverStrategy)
    registry.register("bollinger_bounce", BollingerBounceStrategy)
    registry.register("bias_reversal", BiasReversalStrategy)
    registry.register("rsi_bias_combo", RSIBiasComboStrategy)
    return registry
