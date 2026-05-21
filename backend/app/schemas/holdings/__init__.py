"""Pydantic schemas for the Portfolio Tracker API (UNI-PORT-001 Batch D).

These DTOs sit between `app/services/portfolio/*` (Decimal / dataclass-
heavy domain objects) and the HTTP wire (Decimal-as-string per
`CLAUDE.md` line 35).

Decimal serialization strategy
------------------------------
We declare every Decimal field as `Decimal` and attach a
`@field_serializer(..., when_used='json')` method to each response model
that lists its Decimal fields (stored columns *and* `@computed_field`
properties)::

    @field_serializer("amount_per_share", "quantity_at_record", when_used="json")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)

This keeps Decimal values exact on the wire (no float coercion, no
banker's rounding) while still letting service-layer call sites pass
`Decimal(...)` directly. The previous `ConfigDict(json_encoders=...)`
shape was deprecated in Pydantic 2.x and is removed in v3; the
field-serializer form is strongly typed and IDE-friendly.

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
from app.schemas.holdings.import_csv import (
    ImportResult,
    ImportResultRow,
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
    "ImportResult",
    "ImportResultRow",
]
