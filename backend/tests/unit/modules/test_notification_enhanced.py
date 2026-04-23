"""Tests for enhanced notification schemas and endpoints."""

from __future__ import annotations


def test_notification_condition_schema() -> None:
    from app.schemas.notification import NotificationCondition

    c = NotificationCondition(indicator="RSI", operator="<", value=30)
    assert c.indicator == "RSI"
    assert c.operator == "<"
    assert c.value == 30
    assert c.params == {}


def test_notification_condition_with_params() -> None:
    from app.schemas.notification import NotificationCondition

    c = NotificationCondition(
        indicator="RSI", operator="<", value=30, params={"period": 14}
    )
    assert c.params == {"period": 14}


def test_rule_create_multi_condition() -> None:
    from app.schemas.notification import NotificationCondition, NotificationRuleCreate

    rule = NotificationRuleCreate(
        name="Test",
        rule_type="multi_condition",
        symbol="2330.TW",
        conditions=[
            NotificationCondition(indicator="RSI", operator="<", value=30),
            NotificationCondition(indicator="KD_K", operator="<", value=20),
        ],
        condition_logic="AND",
        channels=["telegram"],
    )
    assert len(rule.conditions) == 2
    assert rule.condition_logic == "AND"
    assert rule.channels == ["telegram"]


def test_rule_create_defaults() -> None:
    from app.schemas.notification import NotificationRuleCreate

    rule = NotificationRuleCreate(name="Simple", rule_type="price_alert")
    assert rule.symbol == ""
    assert rule.conditions == []
    assert rule.condition_logic == "AND"
    assert rule.channels == ["telegram"]
    assert rule.schedule is None


def test_rule_response_backward_compatible() -> None:
    from app.schemas.notification import NotificationRuleResponse

    # dict form (backward compatible)
    resp = NotificationRuleResponse(
        id=1,
        name="Test",
        rule_type="price_alert",
        symbol="2330.TW",
        conditions={"price": ">100"},
        condition_logic="AND",
        channels=["telegram"],
        is_active=True,
    )
    assert isinstance(resp.conditions, dict)

    # list form (new multi-condition)
    resp2 = NotificationRuleResponse(
        id=2,
        name="Test2",
        rule_type="multi_condition",
        symbol="2330.TW",
        conditions=[{"indicator": "RSI", "operator": "<", "value": 30}],
        condition_logic="OR",
        channels=["telegram"],
        is_active=True,
    )
    assert isinstance(resp2.conditions, list)


def test_list_channels_endpoint() -> None:
    from app.api.v1.notifications import list_channels

    channels = list_channels()
    assert len(channels) == 4
    ids = [c["id"] for c in channels]
    assert "telegram" in ids
    assert "email" in ids
    assert "line" in ids
    assert "webhook" in ids
    telegram = next(c for c in channels if c["id"] == "telegram")
    assert telegram["status"] == "available"


def test_list_templates_endpoint() -> None:
    from app.api.v1.notifications import list_notification_templates

    templates = list_notification_templates()
    assert len(templates) == 5
    keys = [t["key"] for t in templates]
    assert "price_above" in keys
    assert "rsi_oversold" in keys
    assert "daily_summary" in keys
    assert "big_move" in keys
    assert "multi_indicator" in keys

    multi = next(t for t in templates if t["key"] == "multi_indicator")
    assert len(multi["default_conditions"]) == 2
    assert multi["rule_type"] == "multi_condition"
