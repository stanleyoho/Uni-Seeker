from app.modules.screener.conditions import Condition, ConditionGroup, evaluate_condition


def test_less_than() -> None:
    c = Condition(indicator="RSI", params={"period": 14}, op="<", value=30)
    assert evaluate_condition(c, {"RSI": 25.0}) is True
    assert evaluate_condition(c, {"RSI": 35.0}) is False


def test_greater_than() -> None:
    c = Condition(indicator="RSI", params={}, op=">", value=70)
    assert evaluate_condition(c, {"RSI": 75.0}) is True
    assert evaluate_condition(c, {"RSI": 65.0}) is False


def test_between() -> None:
    c = Condition(indicator="RSI", params={}, op="between", value=[30, 70])
    assert evaluate_condition(c, {"RSI": 50.0}) is True
    assert evaluate_condition(c, {"RSI": 25.0}) is False
    assert evaluate_condition(c, {"RSI": 75.0}) is False


def test_equal() -> None:
    c = Condition(indicator="PE", params={}, op="==", value=15.0)
    assert evaluate_condition(c, {"PE": 15.0}) is True
    assert evaluate_condition(c, {"PE": 16.0}) is False


def test_missing_indicator_returns_false() -> None:
    c = Condition(indicator="RSI", params={}, op="<", value=30)
    assert evaluate_condition(c, {}) is False


def test_condition_group_and() -> None:
    group = ConditionGroup(operator="AND", rules=[
        Condition(indicator="RSI", params={}, op="<", value=30),
        Condition(indicator="KD_K", params={}, op="<", value=20),
    ])
    assert group.evaluate({"RSI": 25.0, "KD_K": 15.0}) is True
    assert group.evaluate({"RSI": 25.0, "KD_K": 25.0}) is False


def test_condition_group_or() -> None:
    group = ConditionGroup(operator="OR", rules=[
        Condition(indicator="RSI", params={}, op="<", value=30),
        Condition(indicator="KD_K", params={}, op="<", value=20),
    ])
    assert group.evaluate({"RSI": 25.0, "KD_K": 50.0}) is True
    assert group.evaluate({"RSI": 50.0, "KD_K": 50.0}) is False


def test_lte_gte() -> None:
    c1 = Condition(indicator="RSI", params={}, op="<=", value=30)
    assert evaluate_condition(c1, {"RSI": 30.0}) is True
    c2 = Condition(indicator="RSI", params={}, op=">=", value=70)
    assert evaluate_condition(c2, {"RSI": 70.0}) is True
