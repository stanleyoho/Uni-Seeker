import json

from pydantic import BaseModel, field_validator


class NotificationCondition(BaseModel):
    """Single notification condition."""

    indicator: str  # "price", "RSI", "MACD", "volume_change", etc.
    operator: str  # ">", "<", ">=", "<=", "crosses_above", "crosses_below"
    value: float
    params: dict[str, object] = {}


class NotificationRuleCreate(BaseModel):
    name: str
    rule_type: str  # "price_alert", "indicator_alert", "multi_condition", "daily_summary"
    symbol: str = ""
    conditions: list[NotificationCondition] = []
    condition_logic: str = "AND"  # AND or OR
    channels: list[str] = ["telegram"]  # telegram, email (future), line (future)
    schedule: str | None = None  # cron expression for scheduled notifications


class NotificationRuleResponse(BaseModel):
    id: int
    name: str
    rule_type: str
    symbol: str
    conditions: list[dict] | dict  # backward compatible
    condition_logic: str
    channels: list[str]
    is_active: bool

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]

    model_config = {"from_attributes": True}


class NotificationRuleListResponse(BaseModel):
    rules: list[NotificationRuleResponse]
    total: int
