"""Trade DTOs for /api/v1/holdings/trades.

Spec §5.4 Table 2 + §6.2 Table 2. Decimal-as-string on the wire is
enforced via `@field_serializer(..., when_used='json')` on the response
model (see package docstring on `app.schemas.holdings`). The legacy
`json_encoders` knob is deprecated in Pydantic 2.x and removed in v3.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.enums import Market

TradeAction = Literal["BUY", "SELL"]


class TradeCreateRequest(BaseModel):
    """POST /holdings/trades body.

    Phase 1 supports only BUY / SELL (spec §13 Phase 1 AC1).
    DIVIDEND / SPLIT come in Phase 3 — added to the Literal then.
    """

    account_id: int
    action: TradeAction
    symbol: str = Field(..., min_length=1, max_length=20)
    market: Market
    qty: Decimal = Field(..., gt=Decimal("0"))
    price: Decimal = Field(..., gt=Decimal("0"))
    fee: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    trade_date: date | None = None
    note: str | None = None


class TradeUpdateRequest(BaseModel):
    """PATCH /holdings/trades/{id} body — every field optional.

    Per Q14.4 "全開放": any field on any trade may change. Service
    layer triggers a full lot-chain rebuild after the PATCH.
    """

    account_id: int | None = None
    action: TradeAction | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    market: Market | None = None
    qty: Decimal | None = Field(default=None, gt=Decimal("0"))
    price: Decimal | None = Field(default=None, gt=Decimal("0"))
    fee: Decimal | None = Field(default=None, ge=Decimal("0"))
    tax: Decimal | None = Field(default=None, ge=Decimal("0"))
    trade_date: date | None = None
    note: str | None = None


class TradeResponse(BaseModel):
    """Trade row as exposed by GET / POST / PATCH.

    `quantity` mirrors the ORM column name (the request payload uses
    the shorter ``qty`` for ergonomics — the API endpoint maps one to
    the other when calling the service).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    market: Market
    action: str
    trade_date: date
    price: Decimal | None
    quantity: Decimal | None
    fee: Decimal
    tax: Decimal
    note: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("price", "quantity", "fee", "tax", when_used="json")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Render Decimal as exact string on the wire (CLAUDE.md line 35).

        Replaces the deprecated `json_encoders={Decimal: str}` knob —
        scheduled for removal in Pydantic v3. `None` stays `None`
        (renders as JSON null — matches spec §12 R8 "missing = null").
        """
        return None if value is None else str(value)
