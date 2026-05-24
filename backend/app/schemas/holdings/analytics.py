"""Analytics DTOs for /api/v1/holdings/analytics — Phase 5.

Mirrors `app.modules.portfolio.analytics.AnalyticsResult` dataclass.
Decimal-as-string per `CLAUDE.md` line 35 — every numeric field is
serialised as JSON string when emitted on the wire (parity with the
other holdings response models).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_serializer


class AnalyticsResponse(BaseModel):
    """TWR / Sharpe / max-drawdown roll-up for a period."""

    twr: Decimal
    twr_annualized: Decimal
    sharpe_ratio: Decimal | None
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    period_days: int
    snapshot_count: int

    @field_serializer(
        "twr",
        "twr_annualized",
        "sharpe_ratio",
        "max_drawdown",
        "max_drawdown_pct",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Render Decimal as exact string, preserving None for Sharpe.

        Sharpe is `None` when we cannot compute a meaningful ratio
        (< 2 returns or zero stdev) — the UI shows "—" for those.
        """
        return None if value is None else str(value)


__all__ = ["AnalyticsResponse"]
