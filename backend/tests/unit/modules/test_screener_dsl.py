"""Unit tests for the composable screener Query DSL compiler (A2)."""

import pytest

from app.modules.screener.conditions import (
    Condition,
    NestedConditionGroup,
)
from app.modules.screener.dsl import (
    DslClause,
    DslCompileError,
    DslGroup,
    compile_group,
)


def test_compile_flat_and_group() -> None:
    """A flat AND group compiles to a NestedConditionGroup of conditions."""
    group = DslGroup(
        op="and",
        clauses=[
            DslClause(field="RSI", cmp="lt", value=30),
            DslClause(field="KD_K", cmp="gt", value=50),
        ],
    )
    compiled = compile_group(group)

    assert isinstance(compiled, NestedConditionGroup)
    assert compiled.operator == "AND"
    assert len(compiled.members) == 2
    assert all(isinstance(m, Condition) for m in compiled.members)
    # cmp words map to symbolic ops.
    rsi, kd = compiled.members
    assert isinstance(rsi, Condition)
    assert rsi.indicator == "RSI"
    assert rsi.op == "<"
    assert isinstance(kd, Condition)
    assert kd.indicator == "KD_K"
    assert kd.op == ">"


def test_compile_nested_and_or() -> None:
    """(RSI < 30) AND ((KD_K < 20) OR (BIAS < -5)) compiles + evaluates."""
    group = DslGroup(
        op="and",
        clauses=[
            DslClause(field="RSI", cmp="lt", value=30),
            DslGroup(
                op="or",
                clauses=[
                    DslClause(field="KD_K", cmp="lt", value=20),
                    DslClause(field="BIAS", cmp="lt", value=-5),
                ],
            ),
        ],
    )
    compiled = compile_group(group)

    assert compiled.operator == "AND"
    assert len(compiled.members) == 2
    inner = compiled.members[1]
    assert isinstance(inner, NestedConditionGroup)
    assert inner.operator == "OR"
    # Flatten reaches every leaf regardless of nesting.
    leaves = {c.indicator for c in compiled.conditions()}
    assert leaves == {"RSI", "KD_K", "BIAS"}


def test_nested_evaluation_semantics() -> None:
    """Boolean tree evaluates with correct AND/OR short-circuit semantics."""
    group = compile_group(
        DslGroup(
            op="and",
            clauses=[
                DslClause(field="RSI", cmp="lt", value=30),
                DslGroup(
                    op="or",
                    clauses=[
                        DslClause(field="KD_K", cmp="lt", value=20),
                        DslClause(field="BIAS", cmp="lt", value=-5),
                    ],
                ),
            ],
        )
    )
    # RSI passes, OR branch satisfied by BIAS -> overall True.
    assert group.evaluate({"RSI": 25.0, "KD_K": 80.0, "BIAS": -10.0}) is True
    # RSI passes but neither OR leaf passes -> False.
    assert group.evaluate({"RSI": 25.0, "KD_K": 80.0, "BIAS": 0.0}) is False
    # RSI fails -> AND is False regardless of OR branch.
    assert group.evaluate({"RSI": 40.0, "KD_K": 5.0, "BIAS": -10.0}) is False


def test_between_comparator() -> None:
    group = compile_group(
        DslGroup(op="and", clauses=[DslClause(field="RSI", cmp="between", value=[40, 60])])
    )
    assert group.evaluate({"RSI": 50.0}) is True
    assert group.evaluate({"RSI": 70.0}) is False


def test_invalid_field_rejected() -> None:
    with pytest.raises(DslCompileError, match="Unknown field"):
        compile_group(DslGroup(op="and", clauses=[DslClause(field="__proto__", cmp="lt", value=1)]))


def test_arbitrary_field_injection_rejected() -> None:
    """A field outside the allowlist (e.g. an SQL-ish string) is rejected."""
    with pytest.raises(DslCompileError, match="Unknown field"):
        compile_group(
            DslGroup(
                op="and",
                clauses=[DslClause(field="RSI; DROP TABLE stocks", cmp="lt", value=1)],
            )
        )


def test_invalid_comparator_rejected() -> None:
    with pytest.raises(DslCompileError, match="Unknown comparator"):
        compile_group(DslGroup(op="and", clauses=[DslClause(field="RSI", cmp="approx", value=1)]))


def test_between_requires_pair() -> None:
    with pytest.raises(DslCompileError, match="between"):
        compile_group(DslGroup(op="and", clauses=[DslClause(field="RSI", cmp="between", value=30)]))


def test_non_numeric_value_rejected() -> None:
    with pytest.raises(DslCompileError, match="numeric"):
        compile_group(
            DslGroup(op="and", clauses=[DslClause(field="RSI", cmp="lt", value="cheap")])  # type: ignore[arg-type]
        )


def test_empty_group_rejected() -> None:
    with pytest.raises(DslCompileError, match="at least one"):
        compile_group(DslGroup(op="and", clauses=[]))


def test_max_depth_guard() -> None:
    """Excessively deep nesting is rejected (DoS hardening)."""
    node: DslGroup = DslGroup(op="and", clauses=[DslClause(field="RSI", cmp="lt", value=1)])
    for _ in range(12):
        node = DslGroup(op="and", clauses=[node])
    with pytest.raises(DslCompileError, match="too deep"):
        compile_group(node)
