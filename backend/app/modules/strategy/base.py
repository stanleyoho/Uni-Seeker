from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Signal:
    """Trading signal."""
    action: str  # "BUY", "SELL", "HOLD"
    symbol: str
    reason: str
    strength: float = 1.0  # 0.0 - 1.0


@dataclass
class StrategyConfig:
    name: str
    description: str
    params: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Strategy(Protocol):
    config: StrategyConfig

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        """Evaluate strategy on price data. Returns latest signal."""
        ...
