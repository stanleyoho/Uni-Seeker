"""CUSIP -> Stock mapping resolver — Phase 2 / UNI-F13-002 CUSIP backfill.

Pure module: no DB writes, no I/O outside SQLAlchemy reads on the passed
``AsyncSession``. Service layer (``app.services.institutional.cusip_backfill_job``)
owns transaction boundaries; this module exposes idempotent read-only
helpers that return ``CusipMatch`` records.

Resolution strategy (in order, first hit wins)
----------------------------------------------
1. **EXACT** — ``stocks.cusip = <cusip>`` (case-sensitive). The most
   trustworthy signal: the stock-master ingester already validated it.
2. **NAME_LIKE** — normalize ``name_of_issuer`` (strip COM/INC/CORP/LP/
   CLASS A etc.), lowercase, then ``LIKE %normalized%`` against
   ``LOWER(stocks.name)``. Best-effort fallback when no Stock has CUSIP
   populated yet. Only accepted when **exactly one** Stock matches —
   ambiguous fuzzy matches collapse to NONE rather than guess.
3. **NONE** — record the CUSIP but leave ``stock_id`` NULL. The 13F
   ingester already accepts unmapped holdings (see
   ``F13Holding.stock_id`` nullable FK).

Phase 3 / UNI-F13-003 adds an **OpenFIGI** layer between EXACT and
NAME_LIKE — opt-in via the ``_with_figi`` variants below. The original
Y3 functions remain untouched and keep their 3-layer behaviour so
service code that chose not to wire FIGI sees zero behavioural change.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import func, select

from app.models.stock import Stock
from app.obs.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.institutional.openfigi_client import OpenFigiClient


__all__ = [
    "CusipMatch",
    "CusipMatchFigi",
    "_normalize_issuer_name",
    "batch_resolve_cusips",
    "batch_resolve_cusips_with_figi",
    "resolve_cusip",
    "resolve_cusip_with_figi",
]


_logger = get_logger(component="cusip_mapper")


# Match confidence tiers used downstream by the backfill job's
# upgrade-path filter (EXACT supersedes NAME_LIKE on re-run).
_CONFIDENCE_EXACT = "EXACT"
_CONFIDENCE_FIGI = "FIGI"
_CONFIDENCE_NAME_LIKE = "NAME_LIKE"
_CONFIDENCE_NONE = "NONE"

_VIA_CUSIP = "stocks.cusip"
_VIA_FIGI = "openfigi"
_VIA_NAME = "name_fuzzy"
_VIA_NONE = "none"


class CusipMatch(NamedTuple):
    """Result row for a single CUSIP resolution attempt.

    ``stock_id`` is None when no candidate was found OR when ``cusip``
    was empty/invalid. ``match_via`` carries the path that produced the
    hit so the backfill job can write structured telemetry.
    """

    cusip: str
    stock_id: int | None
    match_confidence: str  # "EXACT" / "NAME_LIKE" / "NONE"
    match_via: str  # "stocks.cusip" / "name_fuzzy" / "none"
    matched_name: str | None


class CusipMatchFigi(NamedTuple):
    """4-layer resolution result (Phase 3, FIGI-aware).

    Adds two surfaces over :class:`CusipMatch`:

    - ``match_confidence`` may be ``"FIGI"`` when layer 2 succeeds.
    - ``figi_ticker`` carries the resolved ticker even when no local
      ``Stock`` row exists for it — useful for telemetry / backfilling
      ``stocks`` master from confirmed FIGI hits in a later job.

    A FIGI match resolves a ``stock_id`` only when ``Stock.symbol`` is
    present in the local DB; if FIGI returns a ticker we don't carry,
    we still expose it via ``figi_ticker`` (so backfill can record the
    ticker for later master-import) but ``stock_id`` falls through to
    NAME_LIKE / NONE.
    """

    cusip: str
    stock_id: int | None
    match_confidence: str  # "EXACT" / "FIGI" / "NAME_LIKE" / "NONE"
    match_via: str  # "stocks.cusip" / "openfigi" / "name_fuzzy" / "none"
    matched_name: str | None
    figi_ticker: str | None


# ── name normalization ───────────────────────────────────────────────────

# Order matters: longer phrases first so e.g. "CLASS A" is stripped
# before "A" gets confused with the standalone word "A".
_NAME_SUFFIX_TOKENS = (
    "common stock",
    "ordinary shares",
    "class a common stock",
    "class b common stock",
    "class c common stock",
    "preferred stock",
    "depositary shares",
    "depositary receipt",
    "depositary receipts",
    "american depositary",
    "warrants to purchase",
    "warrants",
    "rights",
    "units",
    "class a",
    "class b",
    "class c",
    "class d",
    "series a",
    "series b",
    "corporation",
    "incorporated",
    "limited",
    "company",
    "holdings",
    "inc",
    "corp",
    "ltd",
    "llc",
    "lp",
    "plc",
    "co",
    "sa",
    "ag",
    "nv",
    "com",
    "the",
)

# Strip punctuation that doesn't help fuzzy matching. We keep spaces +
# digits + ascii letters.
_PUNCT_RE = re.compile(r"[.,;:&/'`\"()\\\-]+")
_MULTISPACE_RE = re.compile(r"\s+")


def _normalize_issuer_name(name: str) -> str:
    """Strip COM/INC/CORP/CORPORATION/LP/LLC/LTD/LIMITED/CLASS A/CLASS B etc.

    Returns lowercased trimmed string for fuzzy matching. The intent is
    that "APPLE INC COM" and "APPLE INC. - COMMON STOCK" and "APPLE INC"
    all collapse to the same canonical form ("apple") so LIKE matching
    is meaningful.

    Edge cases handled:
      * Unicode / non-ASCII letters are preserved (don't break BRK-A).
      * Empty / whitespace-only input returns "".
      * Punctuation is stripped before tokenization so "INC." and "INC"
        both qualify as the INC suffix token.
    """
    if not name:
        return ""
    # Lowercase, strip punctuation, collapse whitespace.
    cleaned = _PUNCT_RE.sub(" ", name.lower())
    cleaned = _MULTISPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return ""

    # Repeatedly strip trailing suffix tokens. Some 13F names stack
    # them: "APPLE INC COM CLASS A" → strip "class a", then "com",
    # then "inc" — leaves "apple".
    changed = True
    while changed:
        changed = False
        for token in _NAME_SUFFIX_TOKENS:
            if cleaned == token:
                cleaned = ""
                changed = True
                break
            suffix = " " + token
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip()
                changed = True
                break
        if not cleaned:
            break

    return cleaned


# ── resolution ───────────────────────────────────────────────────────────


async def resolve_cusip(
    db: AsyncSession,
    cusip: str,
    name_of_issuer: str | None = None,
) -> CusipMatch:
    """Best-effort CUSIP -> Stock.id resolution.

    Strategy (in order):
      1. EXACT: ``Stock.cusip = <cusip>``
      2. NAME_LIKE: cleaned ``name_of_issuer`` LIKE ``LOWER(Stock.name)``,
         only when **exactly one** stock matches (ambiguous → NONE).
      3. NONE: no match.

    Returns a fully populated :class:`CusipMatch`. Empty/invalid CUSIPs
    return a NONE match without touching the DB.
    """
    cusip_clean = (cusip or "").strip()
    if not cusip_clean:
        return CusipMatch(
            cusip="",
            stock_id=None,
            match_confidence=_CONFIDENCE_NONE,
            match_via=_VIA_NONE,
            matched_name=None,
        )

    # Layer 1 — EXACT
    exact_stmt = select(Stock.id, Stock.name).where(
        Stock.cusip == cusip_clean,
    )
    result = await db.execute(exact_stmt)
    row = result.first()
    if row is not None:
        return CusipMatch(
            cusip=cusip_clean,
            stock_id=int(row.id),
            match_confidence=_CONFIDENCE_EXACT,
            match_via=_VIA_CUSIP,
            matched_name=row.name,
        )

    # Layer 2 — NAME_LIKE
    normalized = _normalize_issuer_name(name_of_issuer or "")
    if normalized and len(normalized) >= 2:
        like_pattern = f"%{normalized}%"
        fuzzy_stmt = (
            select(Stock.id, Stock.name)
            .where(func.lower(Stock.name).like(like_pattern))
            .limit(2)  # 2 = enough to detect ambiguity
        )
        result = await db.execute(fuzzy_stmt)
        candidates = result.all()
        if len(candidates) == 1:
            cand = candidates[0]
            return CusipMatch(
                cusip=cusip_clean,
                stock_id=int(cand.id),
                match_confidence=_CONFIDENCE_NAME_LIKE,
                match_via=_VIA_NAME,
                matched_name=cand.name,
            )
        # 0 or >=2 → ambiguous, fall through to NONE.

    return CusipMatch(
        cusip=cusip_clean,
        stock_id=None,
        match_confidence=_CONFIDENCE_NONE,
        match_via=_VIA_NONE,
        matched_name=None,
    )


async def batch_resolve_cusips(
    db: AsyncSession,
    cusip_name_pairs: list[tuple[str, str | None]],
) -> list[CusipMatch]:
    """Batch resolution. Returns same-length list, preserving input order.

    Currently a loop over :func:`resolve_cusip`. Future optimization (Phase
    3+): single SQL pass for EXACT layer using ``Stock.cusip IN (...)``
    when the input set is large (>100). For Phase 2 sizes (~typical
    13F has 30–1000 holdings; backfill_global processes ≤10k at a time)
    the per-row roundtrip cost on SQLite/Postgres is negligible.
    """
    out: list[CusipMatch] = []
    for cusip, name in cusip_name_pairs:
        out.append(await resolve_cusip(db, cusip, name))
    return out


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 — 4-layer with OpenFIGI
# ─────────────────────────────────────────────────────────────────────────


async def resolve_cusip_with_figi(
    db: AsyncSession,
    cusip: str,
    name_of_issuer: str | None = None,
    figi_client: OpenFigiClient | None = None,
) -> CusipMatchFigi:
    """4-layer CUSIP -> Stock.id resolution.

    Layers (first hit wins):
      1. **EXACT**     — ``Stock.cusip = <cusip>``
      2. **FIGI**      — OpenFIGI lookup → ``Stock.symbol = ticker``
                         (skipped when ``figi_client is None``)
      3. **NAME_LIKE** — fuzzy name match (single candidate only)
      4. **NONE**      — record CUSIP, leave ``stock_id`` NULL

    ``figi_client`` is optional. When omitted, this function behaves
    exactly like :func:`resolve_cusip` but returns the richer
    :class:`CusipMatchFigi` shape — graceful degradation.

    The FIGI layer captures the resolved ticker on the return value even
    when no local Stock matches it, so the caller can log /
    feature-flag a follow-up "import this ticker" path.
    """
    cusip_clean = (cusip or "").strip()
    if not cusip_clean:
        return CusipMatchFigi(
            cusip="",
            stock_id=None,
            match_confidence=_CONFIDENCE_NONE,
            match_via=_VIA_NONE,
            matched_name=None,
            figi_ticker=None,
        )

    # Layer 1 — EXACT
    exact_stmt = select(Stock.id, Stock.name).where(Stock.cusip == cusip_clean)
    result = await db.execute(exact_stmt)
    row = result.first()
    if row is not None:
        return CusipMatchFigi(
            cusip=cusip_clean,
            stock_id=int(row.id),
            match_confidence=_CONFIDENCE_EXACT,
            match_via=_VIA_CUSIP,
            matched_name=row.name,
            figi_ticker=None,
        )

    # Layer 2 — FIGI (single-CUSIP convenience path; batch callers should
    # use :func:`batch_resolve_cusips_with_figi` for rate-limit efficiency).
    figi_ticker: str | None = None
    if figi_client is not None:
        try:
            mappings = await figi_client.map_cusips([cusip_clean])
        except Exception as exc:
            _logger.warning(
                "cusip_mapper_figi_lookup_failed",
                cusip=cusip_clean,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            mappings = []
        if mappings and mappings[0].ticker:
            figi_ticker = mappings[0].ticker
            symbol_stmt = select(Stock.id, Stock.name).where(Stock.symbol == figi_ticker)
            sym_row = (await db.execute(symbol_stmt)).first()
            if sym_row is not None:
                return CusipMatchFigi(
                    cusip=cusip_clean,
                    stock_id=int(sym_row.id),
                    match_confidence=_CONFIDENCE_FIGI,
                    match_via=_VIA_FIGI,
                    matched_name=sym_row.name,
                    figi_ticker=figi_ticker,
                )

    # Layer 3 — NAME_LIKE
    normalized = _normalize_issuer_name(name_of_issuer or "")
    if normalized and len(normalized) >= 2:
        like_pattern = f"%{normalized}%"
        fuzzy_stmt = (
            select(Stock.id, Stock.name).where(func.lower(Stock.name).like(like_pattern)).limit(2)
        )
        candidates = (await db.execute(fuzzy_stmt)).all()
        if len(candidates) == 1:
            cand = candidates[0]
            return CusipMatchFigi(
                cusip=cusip_clean,
                stock_id=int(cand.id),
                match_confidence=_CONFIDENCE_NAME_LIKE,
                match_via=_VIA_NAME,
                matched_name=cand.name,
                figi_ticker=figi_ticker,
            )

    # Layer 4 — NONE (still expose the figi_ticker if we got one, useful
    # for telemetry / future master-import).
    return CusipMatchFigi(
        cusip=cusip_clean,
        stock_id=None,
        match_confidence=_CONFIDENCE_NONE,
        match_via=_VIA_NONE,
        matched_name=None,
        figi_ticker=figi_ticker,
    )


async def batch_resolve_cusips_with_figi(
    db: AsyncSession,
    cusip_name_pairs: list[tuple[str, str | None]],
    figi_client: OpenFigiClient | None = None,
) -> list[CusipMatchFigi]:
    """Batch 4-layer resolution — rate-limit-efficient FIGI lookups.

    Strategy:
      1. Resolve EXACT for every pair (single pre-pass on local DB).
      2. Collect EXACT-misses into one **batched** FIGI call (chunked
         internally by :meth:`OpenFigiClient.map_cusips`). This is the
         critical optimisation: 1000 EXACT-misses cost 10 HTTP requests
         on the authed tier vs 1000 if we looped :func:`resolve_cusip_with_figi`.
      3. For each FIGI ticker returned, look up ``Stock.symbol`` once.
         Mass-collect those into a single ``WHERE symbol IN (...)`` query.
      4. Fall through unresolved rows to NAME_LIKE per :func:`resolve_cusip`.

    When ``figi_client is None`` this collapses to the same behaviour as
    :func:`batch_resolve_cusips` (but returns the FIGI-shaped tuple).
    """
    if not cusip_name_pairs:
        return []

    # Stage A — empty CUSIPs become NONE immediately; live CUSIPs go on.
    n = len(cusip_name_pairs)
    out: list[CusipMatchFigi | None] = [None] * n
    live_idx: list[int] = []
    live_cusips: list[str] = []
    for i, (cusip, _name) in enumerate(cusip_name_pairs):
        c = (cusip or "").strip()
        if not c:
            out[i] = CusipMatchFigi(
                cusip="",
                stock_id=None,
                match_confidence=_CONFIDENCE_NONE,
                match_via=_VIA_NONE,
                matched_name=None,
                figi_ticker=None,
            )
        else:
            live_idx.append(i)
            live_cusips.append(c)

    # Stage B — EXACT pass via single ``WHERE cusip IN (...)``.
    exact_map: dict[str, tuple[int, str | None]] = {}
    if live_cusips:
        rows = (
            await db.execute(
                select(Stock.id, Stock.name, Stock.cusip).where(Stock.cusip.in_(live_cusips))
            )
        ).all()
        for row in rows:
            if row.cusip:
                exact_map[row.cusip] = (int(row.id), row.name)

    # Apply EXACT hits; collect misses for layer 2.
    miss_idx: list[int] = []
    miss_cusips: list[str] = []
    for pos, cusip in zip(live_idx, live_cusips):
        if cusip in exact_map:
            sid, sname = exact_map[cusip]
            out[pos] = CusipMatchFigi(
                cusip=cusip,
                stock_id=sid,
                match_confidence=_CONFIDENCE_EXACT,
                match_via=_VIA_CUSIP,
                matched_name=sname,
                figi_ticker=None,
            )
        else:
            miss_idx.append(pos)
            miss_cusips.append(cusip)

    # Stage C — FIGI batch lookup over the EXACT-miss set.
    cusip_to_ticker: dict[str, str] = {}
    if figi_client is not None and miss_cusips:
        try:
            mappings = await figi_client.map_cusips(miss_cusips)
        except Exception as exc:
            _logger.warning(
                "cusip_mapper_figi_batch_failed",
                cusip_count=len(miss_cusips),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            mappings = []
        for m in mappings:
            if m.ticker:
                cusip_to_ticker[m.cusip] = m.ticker

    # Single SYMBOL IN (...) query for the tickers we got back.
    ticker_to_stock: dict[str, tuple[int, str | None]] = {}
    if cusip_to_ticker:
        tickers = list(set(cusip_to_ticker.values()))
        rows = (
            await db.execute(
                select(Stock.id, Stock.name, Stock.symbol).where(Stock.symbol.in_(tickers))
            )
        ).all()
        for row in rows:
            if row.symbol:
                ticker_to_stock[row.symbol] = (int(row.id), row.name)

    # Apply FIGI hits; collect remaining misses for layer 3 (NAME_LIKE).
    name_like_idx: list[int] = []
    for pos, cusip in zip(miss_idx, miss_cusips):
        ticker = cusip_to_ticker.get(cusip)
        if ticker and ticker in ticker_to_stock:
            sid, sname = ticker_to_stock[ticker]
            out[pos] = CusipMatchFigi(
                cusip=cusip,
                stock_id=sid,
                match_confidence=_CONFIDENCE_FIGI,
                match_via=_VIA_FIGI,
                matched_name=sname,
                figi_ticker=ticker,
            )
        else:
            name_like_idx.append(pos)

    # Stage D — NAME_LIKE fallback per row (per-row LIKE doesn't trivially
    # batch — Phase 4 may switch to a fulltext index). For each unresolved
    # row, attach the FIGI ticker we *did* get (if any) for telemetry even
    # when no local Stock matched the symbol.
    for pos in name_like_idx:
        cusip, name = cusip_name_pairs[pos][0], cusip_name_pairs[pos][1]
        c = cusip.strip()
        figi_ticker = cusip_to_ticker.get(c)
        normalized = _normalize_issuer_name(name or "")
        candidate_id: int | None = None
        candidate_name: str | None = None
        if normalized and len(normalized) >= 2:
            like_pattern = f"%{normalized}%"
            fuzzy_stmt = (
                select(Stock.id, Stock.name)
                .where(func.lower(Stock.name).like(like_pattern))
                .limit(2)
            )
            candidates = (await db.execute(fuzzy_stmt)).all()
            if len(candidates) == 1:
                candidate_id = int(candidates[0].id)
                candidate_name = candidates[0].name
        if candidate_id is not None:
            out[pos] = CusipMatchFigi(
                cusip=c,
                stock_id=candidate_id,
                match_confidence=_CONFIDENCE_NAME_LIKE,
                match_via=_VIA_NAME,
                matched_name=candidate_name,
                figi_ticker=figi_ticker,
            )
        else:
            out[pos] = CusipMatchFigi(
                cusip=c,
                stock_id=None,
                match_confidence=_CONFIDENCE_NONE,
                match_via=_VIA_NONE,
                matched_name=None,
                figi_ticker=figi_ticker,
            )

    # Defensive — every slot must be filled.
    return [
        m
        if m is not None
        else CusipMatchFigi(
            cusip="",
            stock_id=None,
            match_confidence=_CONFIDENCE_NONE,
            match_via=_VIA_NONE,
            matched_name=None,
            figi_ticker=None,
        )
        for m in out
    ]
