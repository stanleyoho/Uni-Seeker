"""Portfolio domain layer — pure functions / dataclasses / Protocols.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.1.

**Anti-coupling invariant** (spec §11.2): no SQLAlchemy ORM model imports,
no FastAPI imports. The single DB touchpoint is `DailyCloseLivePriceFetcher`,
hidden behind the `LivePriceFetcher` Protocol.
"""
from __future__ import annotations

from app.modules.portfolio.cost_basis import (
    BuyResult,
    CostBasisInputs,
    FIFOResult,
    InsufficientSharesError,
    Lot,
    SellResult,
    apply_buy,
    apply_sell,
    average_cost,
)
from app.modules.portfolio.live_price_fetcher import (
    DailyCloseLivePriceFetcher,
    LivePriceFetcher,
    PriceQuote,
)
from app.modules.portfolio.pnl import (
    DailyChange,
    PortfolioSummary,
    UnrealizedPnL,
    daily_change,
    summarize,
    unrealized,
)

__all__ = [
    # cost_basis
    "Lot",
    "FIFOResult",
    "InsufficientSharesError",
    "CostBasisInputs",
    "BuyResult",
    "SellResult",
    "apply_buy",
    "apply_sell",
    "average_cost",
    # pnl
    "UnrealizedPnL",
    "DailyChange",
    "PortfolioSummary",
    "unrealized",
    "daily_change",
    "summarize",
    # live_price_fetcher
    "PriceQuote",
    "LivePriceFetcher",
    "DailyCloseLivePriceFetcher",
]
