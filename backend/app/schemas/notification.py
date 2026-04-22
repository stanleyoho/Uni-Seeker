from pydantic import BaseModel


class NotificationRuleCreate(BaseModel):
    name: str
    rule_type: str
    symbol: str = ""
    conditions: dict = {}


class NotificationRuleResponse(BaseModel):
    id: int
    name: str
    rule_type: str
    symbol: str
    conditions: dict
    is_active: bool

    model_config = {"from_attributes": True}


class NotificationRuleListResponse(BaseModel):
    rules: list[NotificationRuleResponse]
    total: int
