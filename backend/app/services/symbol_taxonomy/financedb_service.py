"""FinanceDatabase-backed symbol taxonomy service.

FinanceDatabase (https://github.com/JerBouma/FinanceDatabase) is an open
dataset of ~300k symbols with sector / industry / country / exchange
metadata sourced from Yahoo Finance and curated by JerBouma. We use it
as the **source of truth** for US-listed equity sector taxonomy so the
US heatmap (``app/api/v1/heatmap.py``) renders something other than the
TW-only demo fallback.

Why not just call yfinance directly?
    * yfinance is a per-symbol lookup (1 HTTP request / ticker). For
      ~15k US symbols that's ~15k requests, which gets us rate-limited.
    * FinanceDatabase is a single pip-installable parquet file —
      offline, deterministic, zero network calls at lookup time.
    * The taxonomy is GICS-compatible (Information Technology,
      Financials, Health Care, etc.), which is the schema our
      ``industries`` table already uses.

Public API:
    * ``get_us_equity_universe()`` — list of ``EquityRecord`` for every
      US-listed equity with a known sector. Used by the backfill
      script to do bulk updates.
    * ``enrich_stock(symbol)`` — single-symbol lookup. Used by ad-hoc
      symbol-onboarding flows (e.g. add-watchlist).

Both functions cache the underlying DataFrame in module state. The
first call pays a ~200ms parquet-load cost; subsequent calls are O(1).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import financedatabase as fd  # type: ignore[import-untyped]
import pandas as pd

# US exchange MIC codes (Market Identifier Codes) that we count as
# "US-listed". Excludes European/Asian listings of US-headquartered
# companies (the FinanceDatabase ``country == United States`` filter
# alone returns ~31k rows including ADRs on FRA/STU/BER, which we do
# not want on the US heatmap).
_US_EXCHANGE_CODES: frozenset[str] = frozenset(
    {
        "NMS",  # NASDAQ Global Select
        "NCM",  # NASDAQ Capital Market
        "NGM",  # NASDAQ Global Market
        "NYQ",  # New York Stock Exchange
        "ASE",  # NYSE American (formerly AMEX)
        "PCX",  # NYSE Arca
        "BTS",  # BATS / Cboe BZX
        "PNK",  # OTC Markets (pink sheets) — included so OTC listings
        # like ATSG, etc., still get sector data
    }
)


@dataclass(frozen=True)
class EquityRecord:
    """Minimal sector/industry record for one symbol.

    Attributes
    ----------
    symbol:
        The plain ticker (no exchange suffix). FinanceDatabase keys
        rows on the bare symbol so we surface the same here.
    name:
        Company name from FinanceDatabase (already cleaned).
    sector:
        GICS Level 1 sector (e.g. "Information Technology"). May be
        ``None`` for symbols where FinanceDatabase has no taxonomy
        (warrants, units, SPACs).
    industry:
        GICS Level 2 industry (e.g. "Semiconductors"). May be ``None``.
    country:
        ISO-style country name. For US-listed equities this is always
        "United States" — surfaced so callers can build a multi-region
        taxonomy in future.
    """

    symbol: str
    name: str
    sector: str | None
    industry: str | None
    country: str


# Module-level cache, populated on first call. Guarded by a lock so
# concurrent requests (FastAPI workers) don't double-load the parquet.
_universe_cache: list[EquityRecord] | None = None
_symbol_index: dict[str, EquityRecord] | None = None
_cache_lock = threading.Lock()


def _is_real_value(v: Any) -> bool:
    """pandas-aware truthiness check.

    FinanceDatabase encodes missing taxonomy as ``np.nan`` in object
    columns. ``pd.isna`` correctly handles both ``np.nan`` and
    ``None``; bare ``if v is None`` would miss NaN. Empty strings
    also count as missing.
    """
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        # pd.isna raises on non-array, non-scalar types — assume real.
        pass
    return bool(str(v).strip())


def _str_or_none(v: Any) -> str | None:
    return str(v).strip() if _is_real_value(v) else None


def _load_universe() -> tuple[list[EquityRecord], dict[str, EquityRecord]]:
    """Load the US-listed equity universe from FinanceDatabase.

    Filters:
        * country == "United States"
        * exchange in ``_US_EXCHANGE_CODES``
        * symbol contains no ``.`` (excludes foreign listings of US firms
          like "AAPL.MX" — those are not on US tape).

    Returns
    -------
    tuple
        ``(records, symbol_index)`` — records is a list, symbol_index
        is a dict for O(1) ``enrich_stock`` lookup. Both are computed
        in the same pass to avoid iterating twice.
    """
    equities = fd.Equities()
    df = equities.select(country="United States")
    df = df[df["exchange"].isin(_US_EXCHANGE_CODES)]
    df = df.reset_index()  # symbol moves from index to column
    # FinanceDatabase has stray trailing whitespace on a handful of
    # symbols (e.g. ``"ECC           "`` next to ``"ECC"``). Strip
    # before downstream filters so dedup catches both as one row.
    df["symbol"] = df["symbol"].astype(str).str.strip()
    # Drop foreign-listing suffixes ("BRK.A" etc — these are real US
    # but pandas filter below also kills them; in practice they have
    # alternative tickers like "BRK-A" on NYQ already).
    df = df[~df["symbol"].str.contains(r"\.", regex=True, na=False)]
    # Deduplicate on symbol (FinanceDatabase has dupes for some symbols
    # listed on multiple US exchanges, e.g. NYQ + ASE, plus the
    # whitespace-twin pair noted above). Keep first.
    df = df.drop_duplicates(subset=["symbol"], keep="first")

    records: list[EquityRecord] = []
    index: dict[str, EquityRecord] = {}
    for row in df.itertuples(index=False):
        symbol = str(getattr(row, "symbol", "")).strip()
        if not symbol:
            continue
        rec = EquityRecord(
            symbol=symbol,
            name=_str_or_none(getattr(row, "name", None)) or symbol,
            sector=_str_or_none(getattr(row, "sector", None)),
            industry=_str_or_none(getattr(row, "industry", None)),
            country="United States",
        )
        records.append(rec)
        index[symbol] = rec
    return records, index


def _ensure_cache() -> None:
    global _universe_cache, _symbol_index
    if _universe_cache is not None and _symbol_index is not None:
        return
    with _cache_lock:
        # Double-checked locking: a concurrent caller may have populated
        # the cache while we were waiting on the lock.
        if _universe_cache is not None and _symbol_index is not None:
            return
        records, index = _load_universe()
        _universe_cache = records
        _symbol_index = index


def get_us_equity_universe() -> list[EquityRecord]:
    """Return the full US-listed equity universe (cached).

    Roughly ~15k symbols. The list is sorted by symbol for stable
    iteration (so the backfill script produces deterministic logs).
    """
    _ensure_cache()
    assert _universe_cache is not None  # for type-checker after _ensure_cache
    return sorted(_universe_cache, key=lambda r: r.symbol)


def enrich_stock(symbol: str) -> EquityRecord | None:
    """Look up a single symbol's sector/industry. Returns ``None`` if
    the symbol isn't in the US-listed universe (caller should fall back
    to its existing logic — typically yfinance ``Ticker.info``).
    """
    if not symbol:
        return None
    _ensure_cache()
    assert _symbol_index is not None  # for type-checker after _ensure_cache
    return _symbol_index.get(symbol.strip().upper())


def reset_cache() -> None:
    """Clear the module cache. Test-only — production never calls this."""
    global _universe_cache, _symbol_index
    with _cache_lock:
        _universe_cache = None
        _symbol_index = None
