from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    values: dict[str, list[Any]]


@runtime_checkable
class Indicator(Protocol):
    name: str
    def calculate(self, closes: list[float], **params: object) -> IndicatorResult: ...
