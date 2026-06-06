"""Factor service: load OHLCV and compute the Alpha158-style factor set.

This is the *composition* layer that wires the pure factor functions in
:mod:`app.modules.factors` to the persisted price data (``StockPrice``). It
lives under ``app.services`` (not ``app.modules``) because it performs DB
I/O and orchestrates a benchmark lookup for the cross-asset beta factor —
both service-composition concerns, consistent with the import-linter
``services -> modules`` allowed edge.
"""

from __future__ import annotations

from app.services.factors.service import (
    SymbolFactors,
    compute_symbol_factors,
)

__all__ = ["SymbolFactors", "compute_symbol_factors"]
