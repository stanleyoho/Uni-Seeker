"""PriceLookupRepo — read-only window into the existing `stock_prices`
table for the portfolio Live Price Fetcher path (spec §5.3 + §8).

This repo does NOT modify portfolio tables. It only reads
`stock_prices` rows so the service layer can compute last_price /
prev_close for unrealized P&L (§7.1) and daily change (§7.3).

Symbol resolution: `stock_prices.stock_id` is an INTEGER FK to
`stocks.id`, while the portfolio module trades in `symbol` strings
(e.g. "2330", "AAPL"). This repo therefore joins via `stocks.symbol`
internally so callers can pass symbols directly — they should not
need to know about the integer id surface.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.price import StockPrice
from app.models.stock import Stock

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PriceLookupRepo:
    """Read-only. Never writes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def latest_two_closes(self, symbol: str) -> list[StockPrice]:
        """The two most recent `stock_prices` rows for `symbol`, latest
        first. Returns 0, 1, or 2 rows depending on history depth.

        Note: spec brief calls the parameter `stock_id: str`; in practice
        the model column is `stock_id INTEGER → stocks.id`, and the
        external identifier is `stocks.symbol`. We accept the symbol
        string and resolve via JOIN to keep callers schema-clean.
        """
        result = await self.db.execute(
            select(StockPrice)
            .join(Stock, Stock.id == StockPrice.stock_id)
            .where(Stock.symbol == symbol)
            .order_by(StockPrice.date.desc())
            .limit(2)
        )
        return list(result.scalars().all())

    async def latest_two_closes_batch(self, symbols: list[str]) -> dict[str, list[StockPrice]]:
        """Same as `latest_two_closes` but for many symbols at once —
        used by the portfolio summary endpoint to avoid N+1 queries.

        Returns `{symbol: [latest, prev]}`. Missing symbols simply do
        not appear in the dict; the service layer treats absence as
        "price unavailable" (spec §12 R8).

        Implementation note: pulls the latest N rows per symbol via a
        single query, then partitions in Python. We could express this
        more tightly with a window function (`ROW_NUMBER() OVER (PARTITION
        BY ...)`), but window-function support across PG / SQLite (test)
        works for read-only queries and a Python partition is clearer.
        For ~50 holdings this is well under 100 rows.
        """
        if not symbols:
            return {}
        result = await self.db.execute(
            select(Stock.symbol, StockPrice)
            .join(StockPrice, StockPrice.stock_id == Stock.id)
            .where(Stock.symbol.in_(symbols))
            .order_by(Stock.symbol.asc(), StockPrice.date.desc())
        )
        grouped: dict[str, list[StockPrice]] = defaultdict(list)
        for sym, price in result.all():
            if len(grouped[sym]) < 2:
                grouped[sym].append(price)
        return dict(grouped)
