"""Live price feed — Protocol + Phase 1 daily-close impl + Phase 2 intraday impl.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §8.

Phase 1 has no realtime feed (see §8.1: all existing sources are daily close).
We define a Protocol so future Phase 2 realtime impls (`TWSELivePriceFetcher`,
`YFinanceLivePriceFetcher`) are drop-in replacements.

`DailyCloseLivePriceFetcher` is the **only** place domain layer touches the DB,
which is unavoidable: a price feed is intrinsically a query. The coupling is
isolated to one class behind a Protocol — service layer depends on the Protocol,
not the impl.

Phase 2 (§13) adds `YFinanceLivePriceFetcher` for intraday quotes plus an
in-memory per-symbol TTL cache (`TTLCacheMixin`) to limit network calls.
`CachedDailyCloseLivePriceFetcher` wraps the Phase 1 DB impl in the same cache
for testability and as a fallback when external APIs are unavailable.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

import structlog

__all__ = [
    "CachedDailyCloseLivePriceFetcher",
    "CompositeLivePriceFetcher",
    "DailyCloseLivePriceFetcher",
    "LivePriceFetcher",
    "PriceQuote",
    "TTLCacheMixin",
    "YFinanceLivePriceFetcher",
]

logger = structlog.get_logger()


@dataclass(frozen=True)
class PriceQuote:
    """One stock's last-price + prev-close snapshot.

    `stock_id` is the domain-level stock identifier (string symbol like
    "2330.TW" or "NVDA"). Service layer translates this to/from the DB FK
    `stocks.id` if needed — domain layer stays string-typed.

    `as_of` reflects the source freshness (latest close date for Phase 1,
    most-recent intraday tick timestamp for Phase 2).
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

    def __init__(self, db_session_factory: Any) -> None:
        """Inject a callable that returns a Session-like context manager.

        We intentionally type this loosely (Any) — the only operations
        used are `with session_factory() as s: s.execute(...).all()`, so any
        SQLAlchemy `sessionmaker` / test double satisfies it.
        """
        self._db_factory = db_session_factory

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
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
    def _fetch_latest_two(session: Any, stock_id: str) -> list[Any]:
        """Return up to 2 most-recent `stock_prices` rows for `stock_id`.

        Each row must expose `.close` and `.date` (or `.as_of`). The query
        is kept inline rather than living in a repository because this class
        is the single domain-layer DB touchpoint by design (spec §8.3).
        """
        from sqlalchemy import text

        stmt = text(
            "SELECT close, date FROM stock_prices WHERE stock_id = :sid ORDER BY date DESC LIMIT 2"
        )
        return list(session.execute(stmt, {"sid": stock_id}).all())

    @staticmethod
    def _coerce_as_of(row: Any) -> datetime:
        """Normalize the row's date column to a datetime.

        Phase 1 stock_prices uses Date (no time component); we lift it to
        midnight UTC so the Protocol's `as_of: datetime` invariant holds.
        """
        d = getattr(row, "date", None) or getattr(row, "as_of", None)
        if isinstance(d, datetime):
            return d
        if d is None:
            return datetime.min.replace(tzinfo=UTC)
        # date → datetime at midnight UTC (callers treat as as-of timestamp)
        return datetime(d.year, d.month, d.day, tzinfo=UTC)


# ───────────────────────── Phase 2 — intraday + TTL cache ─────────────────────────


@dataclass
class _CachedQuote:
    """Internal cache entry — pairs a `PriceQuote` with its monotonic expiry."""

    quote: PriceQuote
    expires_at: float  # `time.monotonic()` deadline


class TTLCacheMixin:
    """In-memory per-symbol TTL cache for `PriceQuote` values.

    Design choices (spec §8.4 / §9.2):
      - **Per-symbol expiration** (not global): each cache entry has its own
        deadline so a freshly fetched symbol stays valid even when older
        siblings expire. This maps cleanly to "refresh only what's stale".
      - **`time.monotonic()`** rather than wall-clock — immune to system clock
        adjustments and DST jumps; only relative durations matter for TTL.
      - **Opportunistic purge** via `_purge_expired()` called from
        `_get_cached`. We do not run a background task to keep this layer
        pure-Python and test-friendly. Memory bound is `O(active symbols)`.
      - **No locking**: this mixin is designed for cooperative async use in a
        single event loop; concurrent producers would each compute a quote
        and overwrite — acceptable for read-mostly price quotes.
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._cache: dict[str, _CachedQuote] = {}
        self._ttl: int = ttl_seconds

    def _now(self) -> float:
        """Indirection so tests can monkey-patch a deterministic clock."""
        return time.monotonic()

    def _get_cached(self, symbol: str) -> PriceQuote | None:
        entry = self._cache.get(symbol)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            # Expired — drop and miss.
            self._cache.pop(symbol, None)
            return None
        return entry.quote

    def _set_cached(self, symbol: str, quote: PriceQuote) -> None:
        self._cache[symbol] = _CachedQuote(
            quote=quote,
            expires_at=self._now() + self._ttl,
        )

    def _purge_expired(self) -> int:
        """Drop every entry whose deadline has passed; return number purged."""
        now = self._now()
        stale = [sym for sym, c in self._cache.items() if c.expires_at <= now]
        for sym in stale:
            self._cache.pop(sym, None)
        return len(stale)


class YFinanceLivePriceFetcher(TTLCacheMixin):
    """Phase 2 impl — real intraday quotes from yfinance.

    For each cache-miss symbol we:
      1. Build a `yfinance.Ticker` (sync I/O — offloaded via `asyncio.to_thread`
         to keep the event loop responsive).
      2. Pull a 2-day daily history; the last row is the live/most-recent
         session close, the prior row is the previous close. This matches the
         `last_price` / `prev_close` semantics in `PriceQuote` exactly.
      3. Coerce numbers to `Decimal` via `str(...)` to avoid float artefacts.

    Failure modes (gracefully degraded, never raise mid-batch):
      - empty DataFrame (delisted / unknown symbol)  → symbol omitted from result
      - network / yfinance exception                 → warning logged, omitted
      - single-row history (newly listed)            → `prev_close = last_price`

    Symbols are passed through unchanged — callers must already provide
    yfinance-style tickers (`"2330.TW"`, `"NVDA"`); domain layer never owns
    a symbol translation table.
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        super().__init__(ttl_seconds=ttl_seconds)

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        if not stock_ids:
            return {}

        result: dict[str, PriceQuote] = {}
        misses: list[str] = []

        # Opportunistic cleanup before serving — keeps memory bounded across
        # long-lived fetchers.
        self._purge_expired()

        # 1) serve cache hits.
        for sym in stock_ids:
            cached = self._get_cached(sym)
            if cached is not None:
                result[sym] = cached
            else:
                misses.append(sym)

        if not misses:
            return result

        # 2) fetch misses, one symbol at a time. yfinance supports batched
        # calls via `Tickers(",".join(...))` but its per-ticker error
        # handling is opaque — single-symbol calls give us clean
        # symbol-level failure isolation, which the contract requires.
        for sym in misses:
            quote = await asyncio.to_thread(self._fetch_one_sync, sym)
            if quote is not None:
                self._set_cached(sym, quote)
                result[sym] = quote

        return result

    # NB: separated for testability — monkey-patchable in unit tests, and
    # makes the sync/async boundary explicit.
    def _fetch_one_sync(self, symbol: str) -> PriceQuote | None:
        """Sync yfinance call. Returns None on any failure (logged)."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d", interval="1d")
            if hist is None or getattr(hist, "empty", True):
                logger.warning("yfinance_empty_history", symbol=symbol)
                return None

            closes = hist["Close"].tolist()
            indices = list(hist.index)
            if not closes:
                logger.warning("yfinance_no_close_values", symbol=symbol)
                return None

            last_price = Decimal(str(closes[-1]))
            prev_close = Decimal(str(closes[-2])) if len(closes) >= 2 else last_price
            as_of = self._coerce_as_of(indices[-1])
            return PriceQuote(
                stock_id=symbol,
                last_price=last_price,
                prev_close=prev_close,
                as_of=as_of,
            )
        except Exception as exc:
            logger.warning(
                "yfinance_fetch_failed",
                symbol=symbol,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

    @staticmethod
    def _coerce_as_of(idx: object) -> datetime:
        """Best-effort conversion of a pandas Timestamp / datetime / date."""
        if isinstance(idx, datetime):
            return idx
        # pandas Timestamp exposes `.to_pydatetime()`; fall back gracefully.
        to_pydt = getattr(idx, "to_pydatetime", None)
        if callable(to_pydt):
            try:
                value = to_pydt()
                if isinstance(value, datetime):
                    return value
            except Exception:
                pass
        year = getattr(idx, "year", None)
        month = getattr(idx, "month", None)
        day = getattr(idx, "day", None)
        if year and month and day:
            return datetime(year, month, day, tzinfo=UTC)
        return datetime.min.replace(tzinfo=UTC)


class CachedDailyCloseLivePriceFetcher(TTLCacheMixin):
    """Phase 1 daily-close impl wrapped with the Phase 2 TTL cache.

    Useful as:
      - a deterministic test double for the service layer
      - a fallback when yfinance / external APIs are unavailable

    Delegates the cache-miss path to a `DailyCloseLivePriceFetcher` instance.
    """

    def __init__(self, db_session_factory: Any, ttl_seconds: int = 300) -> None:
        super().__init__(ttl_seconds=ttl_seconds)
        self._inner = DailyCloseLivePriceFetcher(db_session_factory)

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        if not stock_ids:
            return {}

        self._purge_expired()

        result: dict[str, PriceQuote] = {}
        misses: list[str] = []
        for sym in stock_ids:
            cached = self._get_cached(sym)
            if cached is not None:
                result[sym] = cached
            else:
                misses.append(sym)

        if not misses:
            return result

        fetched = await self._inner.fetch_quotes(misses)
        for sym, quote in fetched.items():
            self._set_cached(sym, quote)
            result[sym] = quote
        return result


# ───────────────────────── Composite (primary + fallback) ─────────────────────────


class CompositeLivePriceFetcher:
    """Two-tier fetcher: tries `primary` first, falls back to `secondary`
    for any symbols the primary fetcher did not return.

    Production wiring (spec §8.4 / §8.5):
      - **primary**   = `YFinanceLivePriceFetcher` (intraday, may be flaky /
        rate-limited; partial result is the norm, not the exception)
      - **secondary** = `CachedDailyCloseLivePriceFetcher` (DB-backed, always
        available for any symbol that has at least one `stock_prices` row)

    Contract semantics:
      - Primary wins on key overlap. If both fetchers return a quote for the
        same symbol, the primary's value is preserved — `dict.update`-style
        merge with the primary as the authority. Overlap should not happen
        in normal operation (we only ask the secondary about symbols the
        primary failed to deliver) but we keep this invariant explicit so
        the merge is deterministic under any future refactor.
      - Missing-on-both is acceptable: callers already tolerate a partial
        dict (spec §12 R8 — `last_price=None` flows through service →
        schema → UI "—").
      - Never raises mid-batch. A secondary exception is treated like a
        miss and logged via `structlog` so ops can spot a degraded path.

    Logging: when fallback is engaged we emit one `composite_fallback_engaged`
    event with the symbol list — useful for tracking yfinance reliability
    over time without spamming a line per symbol.
    """

    def __init__(
        self,
        primary: LivePriceFetcher,
        secondary: LivePriceFetcher,
    ) -> None:
        self._primary = primary
        self._secondary = secondary

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        if not stock_ids:
            return {}

        # 1) Primary attempt — tolerated to raise *or* return partial.
        try:
            primary_result = await self._primary.fetch_quotes(stock_ids)
        except Exception as exc:
            logger.warning(
                "composite_primary_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                symbols=list(stock_ids),
            )
            primary_result = {}

        # 2) Identify the symbols the primary did not deliver.
        missing = [sid for sid in stock_ids if sid not in primary_result]
        if not missing:
            return primary_result

        # 3) Engage fallback for the gap; log once with the full list so
        # ops can correlate spikes with upstream incidents.
        logger.warning(
            "composite_fallback_engaged",
            missing_symbols=missing,
            missing_count=len(missing),
            requested_count=len(stock_ids),
        )

        try:
            secondary_result = await self._secondary.fetch_quotes(missing)
        except Exception as exc:
            logger.warning(
                "composite_secondary_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                symbols=list(missing),
            )
            secondary_result = {}

        # 4) Merge — primary wins on overlap (defensive; shouldn't occur).
        merged: dict[str, PriceQuote] = dict(secondary_result)
        merged.update(primary_result)
        return merged
