"""Compute a symbol's Alpha158-style factor vector from persisted prices.

Flow
====
1. Resolve the symbol to a ``Stock`` (404 upstream if unknown).
2. Load its ``StockPrice`` history oldest-first into an OHLCV DataFrame.
3. Evaluate the pure factor registry (:func:`compute_factor_vector`).
4. Best-effort beta: if a benchmark series is available, compute beta;
   otherwise leave it ``None`` (never fail the whole vector on a missing
   benchmark).

The function is async only because it awaits the DB; the *math* is delegated
entirely to the pure functions in :mod:`app.modules.factors`, keeping I/O and
computation cleanly separated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.factors import (
    FACTORS,
    beta_to_index,
    composite_momentum_score,
    compute_factor_vector,
)

# Per-market benchmark used for the cross-asset beta factor. 0050.TW tracks
# the TAIEX top-50 and is the de-facto TW market proxy already used by
# app/api/v1/macro.py. US/other markets have no wired benchmark yet -> beta
# is reported as None rather than guessed.
_BENCHMARK_BY_MARKET = {
    "TW_TWSE": "0050.TW",
    "TW_TPEX": "0050.TW",
}

# Beta needs this many trailing daily returns to be meaningful.
_BETA_WINDOW = 60


@dataclass(frozen=True)
class SymbolFactors:
    """The full factor result for one symbol."""

    symbol: str
    bar_count: int
    factors: dict[str, float | None]
    composite_momentum: float | None


async def _load_ohlcv(db: AsyncSession, stock_id: int) -> pd.DataFrame:
    """Load a stock's price history oldest-first as an OHLCV DataFrame."""
    rows = (
        (
            await db.execute(
                select(StockPrice)
                .where(StockPrice.stock_id == stock_id)
                .order_by(StockPrice.date.asc())
            )
        )
        .scalars()
        .all()
    )
    return pd.DataFrame(
        {
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [float(r.volume) for r in rows],
        }
    )


async def _load_benchmark(db: AsyncSession, market: str) -> pd.DataFrame | None:
    """Load the per-market benchmark OHLCV, or ``None`` if not available."""
    symbol = _BENCHMARK_BY_MARKET.get(market)
    if symbol is None:
        return None
    stock = (await db.execute(select(Stock).where(Stock.symbol == symbol))).scalar_one_or_none()
    if stock is None:
        return None
    df = await _load_ohlcv(db, stock.id)
    return df if not df.empty else None


async def compute_symbol_factors(db: AsyncSession, stock: Stock) -> SymbolFactors:
    """Compute the Alpha158-style factor vector for ``stock``.

    The caller is responsible for resolving the symbol to a ``Stock`` (via
    ``get_stock_or_404``) so this function can be reused by batch callers
    that already hold the ORM object.
    """
    df = await _load_ohlcv(db, stock.id)
    factors = compute_factor_vector(df)

    # Best-effort cross-asset beta. Self-beta of the benchmark vs itself is
    # 1.0, which is correct and harmless; we don't special-case it.
    beta: float | None = None
    benchmark = await _load_benchmark(db, stock.market)
    if benchmark is not None and not df.empty:
        beta = beta_to_index(df, benchmark, window=_BETA_WINDOW)
    factors["BETA60"] = beta

    return SymbolFactors(
        symbol=stock.symbol,
        bar_count=len(df),
        factors=factors,
        composite_momentum=composite_momentum_score(df),
    )


def factor_catalog() -> list[tuple[str, str]]:
    """Return ``(name, formula)`` for every registered factor + beta.

    Used by the ``/factors`` listing endpoint as living documentation. Beta
    is appended here because it lives in the service (needs a benchmark), not
    the pure ``FACTORS`` registry.
    """
    catalog = [(spec.name, spec.formula) for spec in FACTORS.values()]
    catalog.append(("BETA60", "cov(r_sym, r_idx) / var(r_idx) over 60d vs 0050.TW"))
    return catalog
