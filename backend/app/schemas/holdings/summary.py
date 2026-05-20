"""Summary DTO for /api/v1/holdings/summary.

Flat mapping of the domain `PortfolioSummary` dataclass; spec §7.4.
`position_count` and `account_count` are added at the API layer for
frontend convenience (UI shows them as KPI badges).
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_serializer


class SummaryResponse(BaseModel):
    """User-wide (or per-account) KPI row."""

    total_cost: Decimal
    total_value: Decimal
    total_unrealized_pnl: Decimal
    total_daily_change: Decimal
    gain_simple: Decimal
    gain_simple_pct: Decimal
    position_count: int
    account_count: int

    @field_serializer(
        "total_cost",
        "total_value",
        "total_unrealized_pnl",
        "total_daily_change",
        "gain_simple",
        "gain_simple_pct",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal) -> str:
        """Render Decimal as exact string on the wire (CLAUDE.md line 35).

        Replaces the deprecated `json_encoders={Decimal: str}` knob —
        scheduled for removal in Pydantic v3.
        """
        return str(value)
