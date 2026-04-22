from app.modules.indicators.base import Indicator


class IndicatorRegistry:
    def __init__(self) -> None:
        self._indicators: dict[str, Indicator] = {}

    def register(self, indicator: Indicator) -> None:
        if indicator.name in self._indicators:
            raise ValueError(f"Indicator '{indicator.name}' already registered")
        self._indicators[indicator.name] = indicator

    def get(self, name: str) -> Indicator:
        if name not in self._indicators:
            raise KeyError(f"Indicator '{name}' not found: unknown")
        return self._indicators[name]

    def list_names(self) -> list[str]:
        return list(self._indicators.keys())
