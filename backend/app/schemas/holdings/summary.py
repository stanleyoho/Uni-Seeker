"""Summary DTO for /api/v1/holdings/summary.

Flat mapping of the domain `PortfolioSummary` dataclass; spec §7.4.
`position_count` and `account_count` are added at the API layer for
frontend convenience (UI shows them as KPI badges).
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    """User-wide (or per-account) KPI row."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    total_cost: Decimal
    total_value: Decimal
    total_unrealized_pnl: Decimal
    total_daily_change: Decimal
    gain_simple: Decimal
    gain_simple_pct: Decimal
    position_count: int
    account_count: int
