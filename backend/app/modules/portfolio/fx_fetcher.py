"""FX rate fetcher — yfinance + TTL cache (Phase 4+ FX support).

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11
      ("FX support" extensibility).

Pattern follows `live_price_fetcher.YFinanceLivePriceFetcher`:
  - yfinance ticker symbol "<BASE><QUOTE>=X" returns one base unit priced in
    quote (e.g. `USDJPY=X` close = 150 means 1 USD = 150 JPY).
  - Sync `yfinance.Ticker.history(...)` is offloaded via `asyncio.to_thread`
    to keep the event loop responsive.
  - In-memory per-pair TTL cache (default 3600s — FX is slow-moving for
    portfolio aggregation purposes).
  - Inverse-pair fallback: if `USDJPY=X` is unavailable, we try `JPYUSD=X`
    and return its reciprocal so callers never have to know about pair
    direction quirks at the API level.
  - Same-currency shortcut: `base == quote` returns `Decimal("1")` with no
    network call.

Symbol contract: callers pass ISO 4217 codes (`"USD"`, `"TWD"`, `"JPY"`,
`"HKD"`). Anything outside `SUPPORTED` is still attempted (we just construct
the yfinance pair string) but emits a warning so ops can spot typos.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog

__all__ = [
    "FxFetchError",
    "FxFetcher",
    "FxQuote",
    "YFinanceFxFetcher",
]

logger = structlog.get_logger()


# ── data class & errors ────────────────────────────────────────────────────


@dataclass(frozen=True)
class FxQuote:
    """One FX rate snapshot.

    `rate` semantics: `quote_amount = base_amount * rate`.
    Example: FxQuote(base="USD", quote="JPY", rate=Decimal("150")) means
    1 USD = 150 JPY → `100 USD * 150 = 15_000 JPY`.
    """

    base: str
    quote: str
    rate: Decimal
    as_of: datetime


class FxFetchError(Exception):
    """Raised when neither direct nor inverse pair could be fetched."""


# ── Protocol-ish base ──────────────────────────────────────────────────────


class FxFetcher:
    """Abstract FX fetcher — concrete impls override `fetch_rate`/`fetch_rates_batch`.

    Kept as a class (not Protocol) because all concrete impls share the
    TTL cache plumbing below. Tests substitute via subclassing or
    monkeypatching `_fetch_one_sync`, mirroring the live_price_fetcher
    pattern.
    """

    async def fetch_rate(
        self, base: str, quote: str, as_of: date | None = None
    ) -> Decimal:  # pragma: no cover - abstract
        raise NotImplementedError

    async def fetch_rates_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], Decimal]:  # pragma: no cover
        raise NotImplementedError


# ── TTL cache helper (per-pair, monotonic clock) ───────────────────────────


@dataclass
class _CachedRate:
    rate: Decimal
    as_of: datetime
    expires_at: float  # `time.monotonic()` deadline


class _FxTTLCache:
    """Per-pair TTL cache — same design as TTLCacheMixin but keyed on
    `(base, quote, as_of_key)` so historical lookups don't collide with spot.

    A historical rate is keyed on `(base, quote, "YYYY-MM-DD")`; a spot rate
    on `(base, quote, None)`.
    """

    def __init__(self, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = ttl_seconds
        self._cache: dict[tuple[str, str, str | None], _CachedRate] = {}

    def _now(self) -> float:
        """Indirection for test monkey-patching."""
        return time.monotonic()

    @staticmethod
    def _key(base: str, quote: str, as_of: date | None) -> tuple[str, str, str | None]:
        return (base, quote, as_of.isoformat() if as_of is not None else None)

    def get(self, base: str, quote: str, as_of: date | None) -> _CachedRate | None:
        k = self._key(base, quote, as_of)
        entry = self._cache.get(k)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._cache.pop(k, None)
            return None
        return entry

    def set(self, base: str, quote: str, as_of: date | None, rate: Decimal, dt: datetime) -> None:
        self._cache[self._key(base, quote, as_of)] = _CachedRate(
            rate=rate,
            as_of=dt,
            expires_at=self._now() + self._ttl,
        )

    def purge_expired(self) -> int:
        now = self._now()
        stale = [k for k, c in self._cache.items() if c.expires_at <= now]
        for k in stale:
            self._cache.pop(k, None)
        return len(stale)


# ── yfinance impl ──────────────────────────────────────────────────────────


class YFinanceFxFetcher(FxFetcher):
    """yfinance-backed FX fetcher with TTL cache.

    Default TTL = 3600s (1h): FX rates change every tick but for portfolio
    aggregation we only need them to within a few minutes; 1h amortizes
    API hits across the typical "load the holdings page" burst.

    Same-currency (`base == quote`) returns `Decimal("1")` without an
    API call.

    Inverse-pair fallback: if `<BASE><QUOTE>=X` returns empty / errors,
    we try `<QUOTE><BASE>=X` and return `1 / rate`. The result is cached
    under the original direction so subsequent hits skip the fallback.
    """

    SUPPORTED = ("TWD", "USD", "JPY", "HKD", "EUR", "GBP", "CNY")

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._cache = _FxTTLCache(ttl_seconds=ttl_seconds)

    # ── public API ────────────────────────────────────────────────────────

    async def fetch_rate(self, base: str, quote: str, as_of: date | None = None) -> Decimal:
        """Return rate such that `quote_amount = base_amount * rate`.

        Raises `FxFetchError` only if both direct and inverse pairs fail.
        Same-currency short-circuits to `Decimal("1")`.
        """
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            return Decimal("1")

        cached = self._cache.get(base, quote, as_of)
        if cached is not None:
            return cached.rate

        # Try direct pair.
        rate, dt = await asyncio.to_thread(self._fetch_one_sync, base, quote, as_of)
        if rate is not None and dt is not None:
            self._cache.set(base, quote, as_of, rate, dt)
            return rate

        # Inverse fallback.
        inv_rate, inv_dt = await asyncio.to_thread(self._fetch_one_sync, quote, base, as_of)
        if inv_rate is not None and inv_dt is not None and inv_rate != Decimal("0"):
            reciprocal = Decimal("1") / inv_rate
            self._cache.set(base, quote, as_of, reciprocal, inv_dt)
            logger.info(
                "fx_fetched_via_inverse",
                base=base,
                quote=quote,
                inverse_rate=str(inv_rate),
                computed_rate=str(reciprocal),
            )
            return reciprocal

        raise FxFetchError(f"could not fetch FX rate {base}/{quote} (direct or inverse)")

    async def fetch_rates_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], Decimal]:
        """Batch fetch — runs each pair sequentially through `fetch_rate`.

        We don't try `yfinance.Tickers(...)` because per-pair failure handling
        gets opaque; per-pair calls are O(N) but each is cached so steady-state
        cost is one API call per uncached pair per hour. Failures for one pair
        do NOT raise; that pair is simply omitted from the result.
        """
        self._cache.purge_expired()
        out: dict[tuple[str, str], Decimal] = {}
        for base, quote in pairs:
            try:
                out[(base, quote)] = await self.fetch_rate(base, quote)
            except FxFetchError as exc:
                logger.warning(
                    "fx_batch_pair_failed",
                    base=base,
                    quote=quote,
                    error=str(exc),
                )
        return out

    # ── sync internals (overridable for tests) ────────────────────────────

    def _fetch_one_sync(
        self, base: str, quote: str, as_of: date | None
    ) -> tuple[Decimal | None, datetime | None]:
        """yfinance call. Returns `(None, None)` on any failure (logged)."""
        if base not in self.SUPPORTED or quote not in self.SUPPORTED:
            logger.warning(
                "fx_unsupported_pair_attempted",
                base=base,
                quote=quote,
                supported=self.SUPPORTED,
            )
        symbol = f"{base}{quote}=X"
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            if as_of is None:
                hist = ticker.history(period="2d", interval="1d")
            else:
                # Historical lookup — start at the requested date, give yfinance
                # a small window for non-trading days.
                hist = ticker.history(
                    start=as_of.isoformat(),
                    interval="1d",
                )
            if hist is None or getattr(hist, "empty", True):
                logger.warning("fx_empty_history", symbol=symbol)
                return None, None

            closes = hist["Close"].tolist()
            indices = list(hist.index)
            if not closes:
                logger.warning("fx_no_close_values", symbol=symbol)
                return None, None

            rate = Decimal(str(closes[-1]))
            dt = self._coerce_as_of(indices[-1])
            return rate, dt
        except Exception as exc:
            logger.warning(
                "fx_fetch_failed",
                symbol=symbol,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None, None

    @staticmethod
    def _coerce_as_of(idx) -> datetime:
        """Best-effort conversion of a pandas Timestamp / datetime / date.

        Mirrors `YFinanceLivePriceFetcher._coerce_as_of` for symmetry; the
        only difference is the fallback to `datetime.utcnow()` instead of
        `datetime.min` because an FX rate without a timestamp is still
        usable (we just don't know the exact tick time).
        """
        if isinstance(idx, datetime):
            return idx
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
        return datetime.now(UTC)
