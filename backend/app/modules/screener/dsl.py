"""Composable Query DSL compiler for the screener (A2).

This module is the *domain* half of the Query DSL: it turns a structured,
recursive AND/OR filter description into the :class:`NestedConditionGroup`
the :class:`~app.modules.screener.engine.ScreenerEngine` evaluates. It owns
field validation (against :data:`app.modules.screener.fields.ALLOWED_FIELDS`)
and operator mapping, but it has **no** knowledge of HTTP or Pydantic — the
API layer parses/validates the request body and hands this module plain
dataclasses (:class:`DslClause` / :class:`DslGroup`). Keeping the compiler
schema-free preserves the import-linter contract "domain modules must not
import the API layer" and keeps the eval logic reusable from tests, the
scheduler, or any future caller.

DSL grammar (conceptual)
========================
::

    group  := { "op": "and" | "or", "clauses": [ clause | group, ... ] }
    clause := { "field": <allowlisted field>,
                "cmp":   "lt" | "lte" | "gt" | "gte" | "eq" | "between",
                "value": number | [number, number] }   # pair for "between"

A ``group`` may nest other groups, giving arbitrary boolean trees such as
``(RSI < 30) AND ((KD_K < 20) OR (BIAS < -5))``.

Comparator mapping
==================
The DSL uses word comparators (``lt``/``gt``/…) on the wire so the JSON is
self-documenting and URL/log-safe; they map 1:1 onto the symbolic operators
that :func:`app.modules.screener.conditions.evaluate_condition` already
understands (``<``/``>``/…). There is exactly one comparison implementation
(in ``conditions``); this module only translates names.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.screener.conditions import Condition, NestedConditionGroup
from app.modules.screener.fields import get_field_spec, is_allowed_field

# Word comparator (DSL wire form) -> symbolic op understood by
# ``evaluate_condition``. The single source of truth for which comparators
# the DSL accepts.
CMP_TO_OP: dict[str, str] = {
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "eq": "==",
    "between": "between",
}

ALLOWED_CMP: frozenset[str] = frozenset(CMP_TO_OP)
ALLOWED_GROUP_OPS: frozenset[str] = frozenset({"and", "or"})


class DslCompileError(ValueError):
    """Raised when a DSL tree fails validation (bad field/cmp/op/value).

    The API layer maps this to a 422 so the client gets a precise reason
    instead of a generic 500.
    """


@dataclass(frozen=True)
class DslClause:
    """A single leaf comparison in the DSL tree."""

    field: str
    cmp: str
    value: object  # number, or [low, high] for "between"


@dataclass(frozen=True)
class DslGroup:
    """An AND/OR group whose members are clauses or sub-groups."""

    op: str  # "and" | "or"
    clauses: list[DslClause | DslGroup] = field(default_factory=list)


def _compile_clause(clause: DslClause) -> Condition:
    if not is_allowed_field(clause.field):
        raise DslCompileError(
            f"Unknown field '{clause.field}'. Field must be one of the "
            f"screener's supported indicators."
        )
    if clause.cmp not in ALLOWED_CMP:
        raise DslCompileError(
            f"Unknown comparator '{clause.cmp}'. Allowed: {', '.join(sorted(ALLOWED_CMP))}."
        )

    op = CMP_TO_OP[clause.cmp]
    value = clause.value

    if op == "between":
        if not (isinstance(value, (list, tuple)) and len(value) == 2):
            raise DslCompileError("'between' requires a 2-element [low, high] value.")
        low, high = value
        if not _is_number(low) or not _is_number(high):
            raise DslCompileError("'between' bounds must be numbers.")
    else:
        if not _is_number(value):
            raise DslCompileError(
                f"Comparator '{clause.cmp}' requires a numeric value, got {type(value).__name__}."
            )

    spec = get_field_spec(clause.field)
    # ``indicator`` is the engine-facing key (== FieldSpec.key); the engine
    # resolves the registry indicator itself by splitting on '_'. Params
    # default to the field's sensible defaults (period 14, etc.).
    return Condition(
        indicator=spec.key,
        params=dict(spec.params),
        op=op,
        value=value,
    )


def _is_number(value: object) -> bool:
    # bool is an int subclass — exclude it so True/False can't sneak in as 1/0.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compile_group(
    group: DslGroup, *, _depth: int = 0, _max_depth: int = 10
) -> NestedConditionGroup:
    """Compile a :class:`DslGroup` into a :class:`NestedConditionGroup`.

    ``_max_depth`` guards against pathologically/maliciously deep trees
    blowing the recursion stack (DoS hardening). Raises
    :class:`DslCompileError` on any invalid node.
    """
    if _depth > _max_depth:
        raise DslCompileError(f"Filter nesting too deep (max {_max_depth}).")

    op = group.op.lower()
    if op not in ALLOWED_GROUP_OPS:
        raise DslCompileError(f"Unknown group operator '{group.op}'. Allowed: and, or.")
    if not group.clauses:
        raise DslCompileError("A group must contain at least one clause.")

    members: list[Condition | NestedConditionGroup] = []
    for member in group.clauses:
        if isinstance(member, DslGroup):
            members.append(compile_group(member, _depth=_depth + 1, _max_depth=_max_depth))
        else:
            members.append(_compile_clause(member))

    # ``NestedConditionGroup`` speaks uppercase AND/OR (matches the legacy
    # ``ConditionGroup`` convention); normalise here.
    return NestedConditionGroup(operator=op.upper(), members=members)
