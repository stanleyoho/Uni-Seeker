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

OpenFIGI integration is **out of scope for Phase 2** (rate-limit
constraints + auth-key plumbing). Logged as Phase 3 backlog.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import func, select

from app.models.stock import Stock

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


__all__ = [
    "CusipMatch",
    "resolve_cusip",
    "batch_resolve_cusips",
    "_normalize_issuer_name",
]


# Match confidence tiers used downstream by the backfill job's
# upgrade-path filter (EXACT supersedes NAME_LIKE on re-run).
_CONFIDENCE_EXACT = "EXACT"
_CONFIDENCE_NAME_LIKE = "NAME_LIKE"
_CONFIDENCE_NONE = "NONE"

_VIA_CUSIP = "stocks.cusip"
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
