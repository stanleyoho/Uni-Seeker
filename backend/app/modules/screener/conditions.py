from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Condition:
    indicator: str
    params: dict[str, Any]
    op: str  # <, >, <=, >=, ==, between
    value: Any


def evaluate_condition(condition: Condition, indicator_values: dict[str, float | None]) -> bool:
    actual = indicator_values.get(condition.indicator)
    if actual is None:
        return False
    match condition.op:
        case "<":
            return actual < condition.value
        case ">":
            return actual > condition.value
        case "<=":
            return actual <= condition.value
        case ">=":
            return actual >= condition.value
        case "==":
            return actual == condition.value
        case "between":
            low, high = condition.value
            return low <= actual <= high
        case _:
            return False


@dataclass
class ConditionGroup:
    operator: str  # AND or OR
    rules: list[Condition] = field(default_factory=list)

    def evaluate(self, indicator_values: dict[str, float | None]) -> bool:
        if self.operator == "AND":
            return all(evaluate_condition(r, indicator_values) for r in self.rules)
        return any(evaluate_condition(r, indicator_values) for r in self.rules)
