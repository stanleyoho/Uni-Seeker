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
from app.modules.portfolio.dividend_processor import (
    CashDividendInputs,
    CashDividendResult,
    StockDividendInputs,
    StockDividendResult,
    process_cash_dividend,
    process_stock_dividend,
)
from app.modules.portfolio.live_price_fetcher import (
    CachedDailyCloseLivePriceFetcher,
    CompositeLivePriceFetcher,
    DailyCloseLivePriceFetcher,
    LivePriceFetcher,
    PriceQuote,
    TTLCacheMixin,
    YFinanceLivePriceFetcher,
)
from app.modules.portfolio.pnl import (
    DailyChange,
    PortfolioSummary,
    UnrealizedPnL,
    daily_change,
    summarize,
    unrealized,
)
from app.modules.portfolio.split_processor import (
    SplitType,
    StockSplitInputs,
    StockSplitResult,
    compute_split_multiplier,
    process_stock_split,
    validate_split_inputs,
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
    "TTLCacheMixin",
    "YFinanceLivePriceFetcher",
    "CachedDailyCloseLivePriceFetcher",
    "CompositeLivePriceFetcher",
    # dividend_processor
    "CashDividendInputs",
    "CashDividendResult",
    "StockDividendInputs",
    "StockDividendResult",
    "process_cash_dividend",
    "process_stock_dividend",
    # split_processor
    "SplitType",
    "StockSplitInputs",
    "StockSplitResult",
    "process_stock_split",
    "compute_split_multiplier",
    "validate_split_inputs",
]
