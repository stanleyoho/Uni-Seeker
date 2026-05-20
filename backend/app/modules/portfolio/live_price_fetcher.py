"""Live price feed — Protocol + Phase 1 daily-close impl.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §8.

Phase 1 has no realtime feed (see §8.1: all existing sources are daily close).
We define a Protocol so future Phase 2 realtime impls (`TWSELivePriceFetcher`,
`YFinanceLivePriceFetcher`) are drop-in replacements.

`DailyCloseLivePriceFetcher` is the **only** place domain layer touches the DB,
which is unavoidable: a price feed is intrinsically a query. The coupling is
isolated to one class behind a Protocol — service layer depends on the Protocol,
not the impl.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

__all__ = [
    "PriceQuote",
    "LivePriceFetcher",
    "DailyCloseLivePriceFetcher",
]


@dataclass(frozen=True)
class PriceQuote:
    """One stock's last-price + prev-close snapshot.

    `stock_id` is the domain-level stock identifier (string symbol like
    "2330.TW" or "NVDA"). Service layer translates this to/from the DB FK
    `stocks.id` if needed — domain layer stays string-typed.

    `as_of` reflects the source freshness (latest close date for Phase 1).
    """

    stock_id: str
    last_price: Decimal
    prev_close: Decimal
    as_of: datetime


class LivePriceFetcher(Protocol):
    """Abstract live price feed. Phase 1: daily-close DB; Phase 2: realtime APIs."""

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:  # pragma: no cover - Protocol method
        ...


class DailyCloseLivePriceFetcher:
    """Phase 1 impl — reads the 2 most recent rows from `stock_prices` per stock.

    For each requested `stock_id`, returns:
      - `last_price` = close of the most-recent date
      - `prev_close` = close of the second-most-recent date
      - `as_of`      = datetime of the most-recent row

    Behaviour for missing data (documented contract, callers depend on this):
      - **stock_id with zero rows**     → omitted from result dict (partial dict).
      - **stock_id with exactly 1 row** → included; `prev_close == last_price`
        (delta = 0, safer than raising mid-batch).

    The async signature is forward-compatible with Phase 2 HTTP-based realtime
    fetchers, even though the SQLAlchemy session call here is sync.
    """

    def __init__(self, db_session_factory) -> None:
        """Inject a callable that returns a Session-like context manager.

        We intentionally type this loosely — the only operations used are
        `with session_factory() as s: s.execute(...).all()`, so any
        SQLAlchemy `sessionmaker` / test double satisfies it.
        """
        self._db_factory = db_session_factory

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
        if not stock_ids:
            return {}

        result: dict[str, PriceQuote] = {}
        with self._db_factory() as session:
            for stock_id in stock_ids:
                rows = self._fetch_latest_two(session, stock_id)
                if not rows:
                    # Missing — partial dict per docstring contract.
                    continue
                latest = rows[0]
                prev = rows[1] if len(rows) >= 2 else latest
                result[stock_id] = PriceQuote(
                    stock_id=stock_id,
                    last_price=Decimal(str(latest.close)),
                    prev_close=Decimal(str(prev.close)),
                    as_of=self._coerce_as_of(latest),
                )
        return result

    @staticmethod
    def _fetch_latest_two(session, stock_id: str):
        """Return up to 2 most-recent `stock_prices` rows for `stock_id`.

        Each row must expose `.close` and `.date` (or `.as_of`). The query
        is kept inline rather than living in a repository because this class
        is the single domain-layer DB touchpoint by design (spec §8.3).
        """
        from sqlalchemy import text

        stmt = text(
            "SELECT close, date FROM stock_prices "
            "WHERE stock_id = :sid "
            "ORDER BY date DESC LIMIT 2"
        )
        return list(session.execute(stmt, {"sid": stock_id}).all())

    @staticmethod
    def _coerce_as_of(row) -> datetime:
        """Normalize the row's date column to a datetime.

        Phase 1 stock_prices uses Date (no time component); we lift it to
        midnight UTC so the Protocol's `as_of: datetime` invariant holds.
        """
        d = getattr(row, "date", None) or getattr(row, "as_of", None)
        if isinstance(d, datetime):
            return d
        if d is None:
            return datetime.min
        # date → datetime at midnight (no tz; callers treat as source-local)
        return datetime(d.year, d.month, d.day)
