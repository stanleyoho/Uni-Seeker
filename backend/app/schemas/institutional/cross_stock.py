"""Cross-stock DTOs — /api/v1/institutional/stocks/{symbol}/institutional.

Spec §5 (cross-stock view) + §8 (`institutional_ownership_panel` Pro
feature). The response answers "which filers hold this stock?" — the
inverse of the per-filer surface.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_serializer


class F13InstitutionalHolderForStock(BaseModel):
    """One filer-row of the per-stock institutional panel.

    `change_type` mirrors the diff engine's 5-way classification but
    here it's a single-side comparison (prev vs current latest holding
    on the same CUSIP).
    """

    filer_id: int
    filer_name: str
    filer_cik: str
    latest_shares: Decimal | None
    latest_value_usd: Decimal | None
    prev_shares: Decimal | None = None
    change_type: str = "UNCHANGED"

    @field_serializer(
        "latest_shares",
        "latest_value_usd",
        "prev_shares",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class F13InstitutionalStockResponse(BaseModel):
    """`GET /institutional/stocks/{symbol}/institutional` envelope."""

    symbol: str
    stock_id: int | None
    holders: list[F13InstitutionalHolderForStock]
