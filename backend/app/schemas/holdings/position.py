"""Position DTOs for /api/v1/holdings/positions.

Service layer returns `PositionWithPnL` (dataclass with `UnrealizedPnL`
/ `DailyChange` nested). The endpoint flattens those into the wire
shape spec §5.4 promised the frontend.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_serializer

from app.models.enums import Market


class PositionResponse(BaseModel):
    """One position row enriched with computed P&L.

    Spec §7.1 / §7.3:
        unrealized_pnl     = (last_price - avg_cost) * qty
        unrealized_pnl_pct = unrealized_pnl / (avg_cost * qty)
        daily_change       = (last_price - prev_close) * qty
        daily_change_pct   = (last_price - prev_close) / prev_close

    `last_price` and the four computed fields may be `null` when the
    symbol has no `stock_prices` history (§12 R8 — UI shows "—").
    """

    account_id: int
    symbol: str
    market: Market
    currency: str
    qty: Decimal
    avg_cost: Decimal | None
    total_cost: Decimal | None
    realized_pnl: Decimal
    last_price: Decimal | None
    prev_close: Decimal | None
    price_as_of: datetime | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_pct: Decimal | None
    daily_change: Decimal | None
    daily_change_pct: Decimal | None
    is_closed: bool

    @field_serializer(
        "qty",
        "avg_cost",
        "total_cost",
        "realized_pnl",
        "last_price",
        "prev_close",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "daily_change",
        "daily_change_pct",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Render Decimal as exact string on the wire (CLAUDE.md line 35).

        Replaces the deprecated `json_encoders={Decimal: str}` knob —
        scheduled for removal in Pydantic v3. `None` stays `None`
        (renders as JSON null — UI shows "—" per spec §12 R8).
        """
        return None if value is None else str(value)


class PositionListResponse(BaseModel):
    """Response envelope for GET /holdings/positions.

    Carries the optional `account_id` filter the caller applied so the
    frontend doesn't need to re-parse the query string.

    No `field_serializer` needed here — `PositionResponse` already
    handles its own Decimal fields, and the envelope itself has none.
    """

    account_id: int | None = None
    positions: list[PositionResponse]
