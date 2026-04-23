from app.modules.indicators.bollinger import BollingerBandsIndicator
from app.modules.indicators.kd import KDIndicator
from app.modules.indicators.macd import MACDIndicator
from app.modules.indicators.moving_average import MovingAverageIndicator
from app.modules.indicators.patterns import PatternIndicator
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.indicators.rsi import RSIIndicator
from app.modules.indicators.volume import VolumeIndicator
from app.modules.indicators.price_volume import PriceVolumeIndicator


def create_default_registry() -> IndicatorRegistry:
    registry = IndicatorRegistry()
    registry.register(RSIIndicator())
    registry.register(MACDIndicator())
    registry.register(KDIndicator())
    registry.register(MovingAverageIndicator())
    registry.register(BollingerBandsIndicator())
    registry.register(VolumeIndicator())
    registry.register(PriceVolumeIndicator())
    registry.register(PatternIndicator())
    return registry
