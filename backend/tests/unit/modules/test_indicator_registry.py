import pytest

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.registry import IndicatorRegistry


class DummyIndicator:
    name = "dummy"
    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        return IndicatorResult(name="dummy", values={"dummy": closes})


def test_registry_register_and_get() -> None:
    registry = IndicatorRegistry()
    dummy = DummyIndicator()
    registry.register(dummy)
    assert registry.get("dummy") is dummy


def test_registry_get_unknown_raises() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(KeyError, match="unknown"):
        registry.get("unknown")


def test_registry_list_indicators() -> None:
    registry = IndicatorRegistry()
    registry.register(DummyIndicator())
    assert "dummy" in registry.list_names()


def test_registry_prevents_duplicate() -> None:
    registry = IndicatorRegistry()
    registry.register(DummyIndicator())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyIndicator())
