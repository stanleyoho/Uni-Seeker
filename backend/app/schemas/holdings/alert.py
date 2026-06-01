"""Pydantic DTOs for /api/v1/holdings/alerts (UNI-ALERT-001).

Decimal-as-string per project convention — the API contract is
``threshold_value: str``. The service consumes ``Decimal`` and Pydantic
converts on the way out.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas._base import StrictModel

RuleTypeLiteral = Literal[
    "POSITION_PRICE_DROP",
    "POSITION_PRICE_RISE",
    "PORTFOLIO_VALUE_ABOVE",
    "PORTFOLIO_VALUE_BELOW",
    "POSITION_PNL_PCT_ABOVE",
    "POSITION_PNL_PCT_BELOW",
]
StatusLiteral = Literal["ACTIVE", "PAUSED", "TRIGGERED"]
ThresholdTypeLiteral = Literal["PCT", "ABSOLUTE"]


class AlertRuleCreateRequest(StrictModel):
    """POST /holdings/alerts body.

    Validation:
      * ``name`` non-empty, <=100 chars.
      * ``threshold_value`` accepted as str/float/int → ``Decimal``.
      * Cross-field validation (rule_type vs symbol/market vs
        threshold_type) lives in the service layer — Pydantic only
        enforces shape, the service enforces semantics.
    """

    name: str = Field(..., min_length=1, max_length=100)
    rule_type: RuleTypeLiteral
    threshold_value: Decimal
    threshold_type: ThresholdTypeLiteral
    symbol: str | None = Field(default=None, max_length=20)
    market: str | None = Field(default=None, max_length=20)


class AlertRuleUpdateRequest(StrictModel):
    """PATCH /holdings/alerts/{id} — every field optional.

    Only ``name``, ``status``, ``threshold_value`` and ``threshold_type``
    are mutable. ``rule_type`` / ``symbol`` / ``market`` are immutable
    so the rule lifecycle stays predictable (re-create if the user
    wants to change scope).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: StatusLiteral | None = None
    threshold_value: Decimal | None = None
    threshold_type: ThresholdTypeLiteral | None = None


class AlertRuleResponse(BaseModel):
    """One alert rule as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: RuleTypeLiteral
    symbol: str | None
    market: str | None
    threshold_value: Decimal
    threshold_type: ThresholdTypeLiteral
    status: StatusLiteral
    last_evaluated_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("threshold_value")
    def _serialise_threshold(self, v: Decimal) -> str:
        # Project convention: numbers go over the wire as strings to
        # protect float precision client-side.
        return str(v)


class AlertEvaluationResponse(BaseModel):
    """POST /holdings/alerts/{id}/evaluate body."""

    triggered: bool
    actual_value: str
    threshold: str
    message: str


__all__ = [
    "AlertEvaluationResponse",
    "AlertRuleCreateRequest",
    "AlertRuleResponse",
    "AlertRuleUpdateRequest",
    "RuleTypeLiteral",
    "StatusLiteral",
    "ThresholdTypeLiteral",
]
