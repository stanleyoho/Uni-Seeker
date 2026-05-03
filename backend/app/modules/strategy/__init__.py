from app.modules.strategy.base import Signal, Strategy, StrategyConfig
from app.modules.strategy.builtin import (
    BiasReversalStrategy,
    BollingerBounceStrategy,
    MACDCrossoverStrategy,
    MACrossoverStrategy,
    RSIBiasComboStrategy,
    RSIOversoldStrategy,
)
from app.modules.strategy.chip import (
    ForeignTrustSyncStrategy,
    InstitutionalFollowStrategy,
    MarginDivergenceStrategy,
    MarginOverleverageStrategy,
    OwnershipConcentrationStrategy,
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

    # Chip-data (籌碼面) strategies
    registry.register("institutional_follow", lambda **kw: InstitutionalFollowStrategy(**kw))
    registry.register("margin_divergence", lambda **kw: MarginDivergenceStrategy(**kw))
    registry.register("foreign_trust_sync", lambda **kw: ForeignTrustSyncStrategy(**kw))
    registry.register("ownership_concentration", lambda **kw: OwnershipConcentrationStrategy(**kw))
    registry.register("margin_overleverage", lambda **kw: MarginOverleverageStrategy(**kw))
    return registry
