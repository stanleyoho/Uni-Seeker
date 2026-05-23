"""Wire schemas for ``/api/v1/holdings/rebalance/preview``.

Phase 5+ Pro-tier rebalancing tool. Same Decimal-as-string convention as
the rest of ``schemas/holdings/`` (see ``summary.py``).

Schema shape:
    RebalanceRequest:
        targets: [RebalanceTarget{symbol, market, target_pct}]
        account_id?: int  — scope the rebalance to one account when set
        min_trade_value?: Decimal  — skip threshold; default 100

    RebalanceResponse:
        total_portfolio_value: Decimal
        suggested_trades: [SuggestedTradeResponse]
        final_allocation_pct: dict[str, Decimal]
        skipped_trades: list[dict]  — pass-through from domain layer
        cash_residual: Decimal
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.enums import Market

__all__ = [
    "RebalanceTarget",
    "RebalanceRequest",
    "SuggestedTradeResponse",
    "RebalanceResponse",
]


class RebalanceTarget(BaseModel):
    """One row of the target allocation. ``target_pct`` is a percentage
    in [0, 100] expressed as Decimal (string-on-the-wire) to preserve
    precision through fractional weights like ``33.333``."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    market: Market
    target_pct: Decimal = Field(ge=0, le=100)


class RebalanceRequest(BaseModel):
    """POST body for ``/holdings/rebalance/preview``.

    ``min_trade_value`` defaults to 100 (server-side default also 100 —
    we mirror it here so the schema is self-documenting). Callers can
    drop to 0 to disable the skip behavior for "exact" rebalancing.
    """

    model_config = ConfigDict(extra="forbid")

    targets: list[RebalanceTarget] = Field(
        default_factory=list,
        description=(
            "Target allocation rows; sum(target_pct) must equal 100 "
            "(±0.01). Empty list signals 'exit every position'."
        ),
    )
    account_id: int | None = Field(
        default=None,
        description=(
            "Restrict the rebalance to one account. When omitted, "
            "aggregates across every account the user owns."
        ),
    )
    min_trade_value: Decimal = Field(
        default=Decimal("100"),
        ge=0,
        description=(
            "Skip suggested trades whose |delta_value| falls below this "
            "threshold (in the position's currency)."
        ),
    )


class SuggestedTradeResponse(BaseModel):
    """One suggested BUY/SELL emitted by the planner. Mirrors
    ``app.modules.portfolio.rebalancing.SuggestedTrade``."""

    symbol: str
    market: Market
    action: Literal["BUY", "SELL"]
    qty: Decimal
    estimated_price: Decimal
    estimated_value: Decimal
    rationale: str

    @field_serializer(
        "qty", "estimated_price", "estimated_value", when_used="json"
    )
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)


class RebalanceResponse(BaseModel):
    """Full preview response.

    ``final_allocation_pct`` keys are ``"{symbol}|{market}"`` strings
    matching the domain layer's composite key. Frontend splits on ``|``
    when rendering the pie chart.

    ``skipped_trades`` items are dicts with at minimum ``symbol``,
    ``market``, ``target_pct``, ``delta_value``, and ``reason`` keys —
    we let the domain shape pass through unchanged so future reasons
    don't require a schema bump.
    """

    total_portfolio_value: Decimal
    suggested_trades: list[SuggestedTradeResponse]
    final_allocation_pct: dict[str, Decimal]
    skipped_trades: list[dict[str, Any]]
    cash_residual: Decimal

    @field_serializer(
        "total_portfolio_value", "cash_residual", when_used="json"
    )
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)

    @field_serializer("final_allocation_pct", when_used="json")
    def _serialize_alloc(self, value: dict[str, Decimal]) -> dict[str, str]:
        return {k: str(v) for k, v in value.items()}
