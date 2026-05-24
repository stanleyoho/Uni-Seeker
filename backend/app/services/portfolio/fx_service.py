"""FX rate service — DB cache (`journal.fx_rates`) + yfinance fallback.

Phase 4+ FX support. Spec §11.

Design notes
------------
- **Reuses the existing `journal.fx_rates` table** (`from_currency`,
  `to_currency`, `date`, `rate`) instead of introducing a parallel
  `portfolio_fx_rates` table — the schema is identical to what we'd need
  and a single source of truth avoids divergent backfill paths.
- **Anti-coupling**: importing `app.models.journal.FXRate` ORM from a
  portfolio service is allowed by spec §11's anti-coupling rule (which
  forbids service→service and domain→ORM coupling, but explicitly permits
  service→cross-namespace ORM reads). We never call `trade_journal`'s
  service from here.
- **Cache strategy** (R + W):
  - READ: look up `fx_rates` for the requested date (or latest row if
    `as_of` is None), within a 30-day staleness window. Stale → fetch.
  - WRITE: every successful fetch is UPSERT'd back into `fx_rates` so
    parallel requests benefit from each other's API calls.
- **Convenience helpers**: `get_rates_for_currencies(set, base)` is the
  one summary_service relies on — returns ``{ccy: rate_to_base}`` with
  ``rate=1`` for the self-pair. Failures for individual currencies are
  re-raised (callers must decide; we don't silently drop because that
  would skew aggregate KPIs).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.journal import FXRate
from app.modules.portfolio.fx_fetcher import FxFetchError, YFinanceFxFetcher
from app.obs.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "FxRateUnavailable",
    "FxService",
]

logger = get_logger("services.portfolio.fx")

# Spot rates older than this are considered stale for "as_of=None" lookups.
# 1 day balances freshness (intraday moves are small for portfolio KPIs)
# vs API cost (free-tier rate limits prefer day-level caching).
_SPOT_STALENESS = timedelta(days=1)


class FxRateUnavailable(Exception):
    """Raised when no rate could be obtained from cache or fetcher."""

    def __init__(self, base: str, quote: str) -> None:
        super().__init__(f"FX rate unavailable: {base} → {quote}")
        self.base = base
        self.quote = quote


class FxService:
    """Resolve FX rates with DB cache + yfinance fallback.

    Lifecycle: instantiated per-request by FastAPI dependency. The injected
    `fetcher` is typically a process-singleton `YFinanceFxFetcher` so its
    in-memory TTL cache is shared across requests; the DB session is
    request-scoped per the usual pattern.
    """

    def __init__(
        self,
        db: AsyncSession,
        fetcher: YFinanceFxFetcher,
    ) -> None:
        self._db = db
        self._fetcher = fetcher

    # ── single-pair API ───────────────────────────────────────────────────

    async def get_rate(
        self,
        base: str,
        quote: str,
        as_of: date | None = None,
    ) -> Decimal:
        """Return rate such that `quote_amount = base_amount * rate`.

        1. Same-currency → 1.
        2. Try DB (`fx_rates`) for the requested date (or most recent row
           within `_SPOT_STALENESS` when `as_of` is None).
        3. On miss/stale → delegate to `_fetcher`, then UPSERT.
        4. Raise `FxRateUnavailable` if both fail.
        """
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            return Decimal("1")

        cached = await self._db_lookup(base, quote, as_of)
        if cached is not None:
            return cached

        try:
            rate = await self._fetcher.fetch_rate(base, quote, as_of=as_of)
        except FxFetchError as exc:
            logger.warning(
                "fx_service_fetcher_failed",
                base=base,
                quote=quote,
                error=str(exc),
            )
            raise FxRateUnavailable(base=base, quote=quote) from exc

        # Persist for future hits. Use the requested date when given;
        # otherwise today (so the "spot" row is keyed deterministically).
        persist_date = as_of or date.today()
        await self._upsert(base, quote, persist_date, rate)
        return rate

    async def convert_amount(
        self,
        amount: Decimal,
        from_ccy: str,
        to_ccy: str,
        as_of: date | None = None,
    ) -> Decimal:
        """Convenience: `amount * get_rate(from, to)`."""
        if amount is None:
            return Decimal("0")
        rate = await self.get_rate(from_ccy, to_ccy, as_of=as_of)
        return amount * rate

    # ── batch helper used by SummaryService ───────────────────────────────

    async def get_rates_for_currencies(
        self,
        currencies: set[str],
        base: str,
    ) -> dict[str, Decimal]:
        """Return ``{ccy: rate_to_base}`` for each currency in the set.

        The base currency itself maps to ``Decimal("1")``. Currencies for
        which neither cache nor fetcher yields a rate raise
        `FxRateUnavailable` (we never silently drop — see module docstring).

        Args:
            currencies: ISO codes present in the user's positions.
            base: the target currency for aggregation.

        Returns:
            ``{ccy: rate}`` mapping. Always non-empty unless `currencies`
            is empty.
        """
        base_u = base.upper()
        out: dict[str, Decimal] = {}
        for ccy in currencies:
            ccy_u = ccy.upper()
            if ccy_u == base_u:
                out[ccy_u] = Decimal("1")
                continue
            out[ccy_u] = await self.get_rate(ccy_u, base_u)
        return out

    # ── DB internals ──────────────────────────────────────────────────────

    async def _db_lookup(
        self,
        base: str,
        quote: str,
        as_of: date | None,
    ) -> Decimal | None:
        """Return the cached rate for (base, quote, as_of) or None.

        For `as_of=None` we accept rows up to `_SPOT_STALENESS` old.
        For explicit `as_of` we accept only an exact-date match — the
        caller asked for a specific historical rate and we should not
        silently substitute a nearby date.
        """
        if as_of is None:
            cutoff = date.today() - _SPOT_STALENESS
            stmt = (
                select(FXRate.rate, FXRate.date)
                .where(
                    FXRate.from_currency == base,
                    FXRate.to_currency == quote,
                    FXRate.date >= cutoff,
                )
                .order_by(FXRate.date.desc())
                .limit(1)
            )
        else:
            stmt = (
                select(FXRate.rate, FXRate.date)
                .where(
                    FXRate.from_currency == base,
                    FXRate.to_currency == quote,
                    FXRate.date == as_of,
                )
                .limit(1)
            )
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        rate_value: Decimal = row[0]
        return rate_value

    async def _upsert(
        self,
        base: str,
        quote: str,
        rate_date: date,
        rate: Decimal,
    ) -> None:
        """Insert or update a single `fx_rates` row.

        We do a portable upsert via SELECT-then-INSERT/UPDATE rather than
        dialect-specific ON CONFLICT, because the codebase targets both
        SQLite (tests) and PostgreSQL (prod) and the table size makes the
        extra round-trip irrelevant (~ tens of rows total).
        """
        existing_stmt = (
            select(FXRate)
            .where(
                FXRate.from_currency == base,
                FXRate.to_currency == quote,
                FXRate.date == rate_date,
            )
            .limit(1)
        )
        result = await self._db.execute(existing_stmt)
        existing = result.scalar_one_or_none()
        if existing is None:
            row = FXRate(
                date=rate_date,
                from_currency=base,
                rate=rate,
                to_currency=quote,
            )
            self._db.add(row)
        else:
            existing.rate = rate
        await self._db.flush()
