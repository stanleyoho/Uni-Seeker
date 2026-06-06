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
            return bool(actual < condition.value)
        case ">":
            return bool(actual > condition.value)
        case "<=":
            return bool(actual <= condition.value)
        case ">=":
            return bool(actual >= condition.value)
        case "==":
            return bool(actual == condition.value)
        case "between":
            low, high = condition.value
            return bool(low <= actual <= high)
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


# --- Composable / nested groups (Query DSL, A2) ----------------------------
#
# ``ConditionGroup`` above is a single-level AND/OR over a flat list of
# conditions — it is what the existing presets and ``ScreenerEngine``
# already speak, so it stays exactly as-is. ``NestedConditionGroup`` is the
# recursive extension the Query DSL compiles onto: a group whose members
# may themselves be conditions OR sub-groups, allowing arbitrary
# ``(A AND (B OR C))`` nesting. Evaluation reuses ``evaluate_condition``
# for the leaves so there is exactly one place where a field/operator/value
# comparison happens (no duplicated eval logic).


@dataclass
class NestedConditionGroup:
    operator: str  # "AND" or "OR"
    members: list["Condition | NestedConditionGroup"] = field(default_factory=list)

    def conditions(self) -> list[Condition]:
        """Flatten every leaf :class:`Condition` reachable from this group.

        Used by the engine to discover which indicators it must compute up
        front (the engine pre-computes indicator values once per symbol,
        keyed by indicator name, so the nesting shape is irrelevant to the
        compute step — only the set of leaf conditions matters).
        """
        out: list[Condition] = []
        for member in self.members:
            if isinstance(member, NestedConditionGroup):
                out.extend(member.conditions())
            else:
                out.append(member)
        return out

    def evaluate(self, indicator_values: dict[str, float | None]) -> bool:
        def _eval(member: "Condition | NestedConditionGroup") -> bool:
            if isinstance(member, NestedConditionGroup):
                return member.evaluate(indicator_values)
            return evaluate_condition(member, indicator_values)

        if self.operator == "AND":
            return all(_eval(m) for m in self.members)
        return any(_eval(m) for m in self.members)
