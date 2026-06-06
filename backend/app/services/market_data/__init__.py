"""Unified market-data provider abstraction (A2 audit item).

Public surface:

* :class:`MarketDataProvider` — the unified Protocol every source adapter
  satisfies.
* :class:`StockQuote` — latest-bar quote type.
* :class:`MarketDataRegistry` / :func:`build_default_registry` — resolver
  that picks the right provider for a symbol.
* :func:`classify_symbol` / :class:`MarketClass` — the routing primitive.

See ``base.py`` for the design rationale.
"""

from __future__ import annotations

from app.services.market_data.base import MarketDataProvider, StockQuote
from app.services.market_data.registry import (
    MarketDataRegistry,
    NoProviderError,
    build_default_registry,
)
from app.services.market_data.symbols import (
    MarketClass,
    classify_symbol,
    to_bare_tw_code,
)

__all__ = [
    "MarketClass",
    "MarketDataProvider",
    "MarketDataRegistry",
    "NoProviderError",
    "StockQuote",
    "build_default_registry",
    "classify_symbol",
    "to_bare_tw_code",
]
