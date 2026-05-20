"""Pydantic schemas for the Portfolio Tracker API (UNI-PORT-001 Batch D).

These DTOs sit between `app/services/portfolio/*` (Decimal / dataclass-
heavy domain objects) and the HTTP wire (Decimal-as-string per
`CLAUDE.md` line 35).

Decimal serialization strategy
------------------------------
We declare every Decimal field as `Decimal` and configure each response
model with::

    model_config = ConfigDict(json_encoders={Decimal: str})

This is the Pydantic-v2-friendly way to keep Decimal values exact on the
wire (no float coercion, no banker's rounding) while still letting
service-layer call sites pass `Decimal(...)` directly.

`None` Decimal values stay `None` (rendered as JSON null) — matches the
"missing quote = null" contract in spec §12 R8.
"""
from app.schemas.holdings.account import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
)
from app.schemas.holdings.dividend import (
    DividendCreateRequest,
    DividendResponse,
    DividendType,
    DividendUpdateRequest,
)
from app.schemas.holdings.position import (
    PositionListResponse,
    PositionResponse,
)
from app.schemas.holdings.summary import SummaryResponse
from app.schemas.holdings.trade import (
    TradeCreateRequest,
    TradeResponse,
    TradeUpdateRequest,
)

__all__ = [
    "AccountCreateRequest",
    "AccountUpdateRequest",
    "AccountResponse",
    "TradeCreateRequest",
    "TradeUpdateRequest",
    "TradeResponse",
    "DividendCreateRequest",
    "DividendUpdateRequest",
    "DividendResponse",
    "DividendType",
    "PositionResponse",
    "PositionListResponse",
    "SummaryResponse",
]
