"""Institutional 13F Pydantic DTOs — 13F Holdings Tracker Phase 1 Batch C.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5 (API endpoints) + §6.6 (schema breakdown).

All Decimal-typed response fields are serialized as JSON strings via
`@field_serializer(..., when_used="json")` to honour CLAUDE.md's
Decimal-as-string contract — the frontend coerces with `Number()` on
read but never receives float-rounded values.
"""

from app.schemas.institutional.cross_stock import (
    F13InstitutionalHolderForStock,
    F13InstitutionalStockResponse,
)
from app.schemas.institutional.filer import (
    F13FilerResponse,
    F13FilerSearchResult,
)
from app.schemas.institutional.filing import (
    F13DiffResponse,
    F13FilingResponse,
    F13HoldingChangeResponse,
    F13HoldingResponse,
    F13HoldingsAtPeriodResponse,
    F13RefreshResponse,
)
from app.schemas.institutional.subscription import (
    F13SubscribeRequest,
    F13SubscriptionResponse,
)

__all__ = [
    "F13DiffResponse",
    # filer
    "F13FilerResponse",
    "F13FilerSearchResult",
    # filing / diff / refresh
    "F13FilingResponse",
    "F13HoldingChangeResponse",
    "F13HoldingResponse",
    "F13HoldingsAtPeriodResponse",
    # cross-stock
    "F13InstitutionalHolderForStock",
    "F13InstitutionalStockResponse",
    "F13RefreshResponse",
    # subscription
    "F13SubscribeRequest",
    "F13SubscriptionResponse",
]
