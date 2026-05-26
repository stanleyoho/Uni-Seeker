"""Wire schemas for ``/api/v1/holdings/rebalance/{preview,execute}``.

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

    RebalanceExecuteResponse (Phase 2):
        executed:  [ExecutedTrade{symbol, market, action, qty, price, trade_id}]
        skipped:   [SkippedTrade{symbol, market, reason, ...}]
        failed:    [FailedTrade{symbol, market, error_code, message}]
        total_executed_value: Decimal
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.enums import Market

__all__ = [
    "ExecutedTrade",
    "FailedTrade",
    "RebalanceExecuteResponse",
    "RebalanceRequest",
    "RebalanceResponse",
    "RebalanceTarget",
    "SkippedTrade",
    "SuggestedTradeResponse",
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
    ``app.modules.portfolio.rebalancing.SuggestedTrade``.

    ``account_id`` (Phase 3) tells the client which broker/portfolio
    account this trade dispatches to when ``execute`` is called. It is
    populated for every trade in single-account previews (echoes the
    request scope) AND for trades sourced from existing positions in
    aggregate previews. It is ``None`` only for brand-new BUYs in
    aggregate mode — the client must scope explicitly before executing.
    """

    symbol: str
    market: Market
    action: Literal["BUY", "SELL"]
    qty: Decimal
    estimated_price: Decimal
    estimated_value: Decimal
    rationale: str
    account_id: int | None = None

    @field_serializer("qty", "estimated_price", "estimated_value", when_used="json")
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

    @field_serializer("total_portfolio_value", "cash_residual", when_used="json")
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)

    @field_serializer("final_allocation_pct", when_used="json")
    def _serialize_alloc(self, value: dict[str, Decimal]) -> dict[str, str]:
        return {k: str(v) for k, v in value.items()}


# ── Phase 2: execute endpoint ───────────────────────────────────────────────


class ExecutedTrade(BaseModel):
    """One suggested trade that was successfully persisted as a real
    ``portfolio_trades`` row.

    ``trade_id`` is the primary key of the inserted row — the UI can
    deep-link to it via ``GET /holdings/trades/{trade_id}``.
    ``account_id`` (Phase 3) is the broker/portfolio account this trade
    landed in. Always populated post-execute.
    """

    symbol: str
    market: Market
    action: Literal["BUY", "SELL"]
    qty: Decimal
    price: Decimal
    trade_id: int
    account_id: int

    @field_serializer("qty", "price", when_used="json")
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)


class SkippedTrade(BaseModel):
    """A suggested trade dropped by the planner BEFORE execution attempt.

    Mirrors the dict shape emitted by ``compute_rebalance.skipped_trades``
    so the frontend can use one schema for both preview and execute. The
    canonical ``reason`` values today are:
      - ``below_min_trade_value``
      - ``missing_price_for_buy``
      - ``missing_price_for_sell``
    """

    symbol: str
    market: str
    reason: str
    target_pct: str | None = None
    delta_value: str | None = None


class FailedTrade(BaseModel):
    """A suggested trade that the planner produced but the trade-write
    pipeline rejected (e.g. ``InsufficientSharesError`` on a SELL whose stale
    snapshot disagrees with the live lot total).

    ``error_code`` matches the canonical ``_detail`` strings (e.g.
    ``insufficient_shares``, ``invalid_trade_input``) so the frontend
    can localise / icon-map identically to the regular trade-create flow.
    ``account_id`` (Phase 3) identifies which account the dispatch was
    targeting; ``None`` for trades that failed before account resolution.
    """

    symbol: str
    market: Market
    action: Literal["BUY", "SELL"]
    error_code: str
    message: str
    account_id: int | None = None


class RebalanceExecuteResponse(BaseModel):
    """Full execute response — per-trade independent commit.

    ``total_executed_value`` is the sum of ``qty * price`` across rows in
    ``executed`` (skipped + failed do NOT count). The UI surfaces it as
    "actually moved $X this rebalance".
    """

    executed: list[ExecutedTrade]
    skipped: list[SkippedTrade]
    failed: list[FailedTrade]
    total_executed_value: Decimal

    @field_serializer("total_executed_value", when_used="json")
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)
