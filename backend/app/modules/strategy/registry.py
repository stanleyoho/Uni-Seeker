from app.modules.strategy.base import Strategy, StrategyConfig


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, type] = {}  # key -> strategy class
        self._defaults: dict[str, dict[str, object]] = {}  # key -> default params

    def register(self, key: str, cls: type, defaults: dict[str, object] | None = None) -> None:
        if key in self._strategies:
            raise ValueError(f"Strategy '{key}' already registered")
        self._strategies[key] = cls
        self._defaults[key] = defaults or {}

    def get(self, key: str, **params: object) -> Strategy:
        if key not in self._strategies:
            available = ", ".join(self._strategies)
            raise KeyError(f"Strategy '{key}' not found. Available: {available}")
        merged = {**self._defaults[key], **params}
        return self._strategies[key](**merged)

    def list_keys(self) -> list[str]:
        return list(self._strategies.keys())

    def list_info(self) -> list[dict[str, object]]:
        result = []
        for key, cls in self._strategies.items():
            instance = cls(**self._defaults[key])
            config: StrategyConfig = instance.config
            result.append(
                {
                    "key": key,
                    "name": config.name,
                    "description": config.description,
                    "params": config.params,
                }
            )
        return result
