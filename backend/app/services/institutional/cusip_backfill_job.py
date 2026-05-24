"""CUSIP backfill job — Phase 2 / UNI-F13-002.

Resolves ``f13_holdings.stock_id`` for rows where the 13F ingester
landed an unmapped CUSIP. Also reverse-populates ``stocks.cusip`` when
we have a confirmed mapping but the Stock row never got its CUSIP set.

Idempotency contract
--------------------
* ``backfill_cusips_for_filer`` / ``backfill_cusips_global`` only touch
  rows where ``stock_id IS NULL``. Re-running on the same data is a
  no-op once every row is either mapped or genuinely unmappable.
* When the EXACT (cusip-column) layer starts succeeding for a holding
  previously matched only by NAME_LIKE, the upgrade path
  (``_upgrade_namelike_to_exact``) replaces the link — also idempotent
  because subsequent runs find the row already EXACT-matched and skip.
* ``backfill_stocks_from_filings`` UPDATEs ``stocks.cusip`` only where
  ``Stock.cusip IS NULL``. Once populated, the row is permanently
  skipped on subsequent runs.

Usage
-----
::

    cd backend && uv run python -m app.services.institutional.cusip_backfill_job

Or programmatically::

    result = await backfill_cusips_for_filer(db, filer_id)

Returns a dict with counters; caller commits the outer transaction.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.db.models.institutional.filing import F13Filing
from app.db.models.institutional.holding import F13Holding
from app.models.stock import Stock
from app.modules.institutional.cusip_mapper import (
    CusipMatch,
    CusipMatchFigi,
    batch_resolve_cusips,
    batch_resolve_cusips_with_figi,
)
from app.obs.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.institutional.openfigi_client import OpenFigiClient


__all__ = [
    "backfill_cusips_for_filer",
    "backfill_cusips_for_filer_with_figi",
    "backfill_cusips_global",
    "backfill_cusips_global_with_figi",
    "backfill_stocks_from_filings",
]

logger = get_logger(component="cusip_backfill")


_EXACT = "EXACT"
_FIGI = "FIGI"
_NAME_LIKE = "NAME_LIKE"


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


async def backfill_cusips_for_filer(
    db: AsyncSession,
    filer_id: int,
    limit: int = 1000,
) -> dict[str, int]:
    """Resolve unmapped holdings for given filer.

    Pulls up to ``limit`` ``f13_holdings`` rows where ``stock_id IS NULL``
    that belong to filings owned by ``filer_id`` (JOIN through
    ``f13_filings.filer_id``). Resolves each via the mapper module and
    persists hits.

    Args:
        db: AsyncSession — caller owns commit.
        filer_id: Restricts the scan to a single filer's filings.
        limit: Max holdings to process this call (back-pressure knob).

    Returns:
        ``{processed, exact_matches, fuzzy_matches, still_unmapped,
        upgraded}`` — counts for telemetry.
    """
    stmt = (
        select(
            F13Holding.id,
            F13Holding.cusip,
            F13Holding.name_of_issuer,
        )
        .join(F13Filing, F13Filing.id == F13Holding.filing_id)
        .where(
            F13Filing.filer_id == filer_id,
            F13Holding.stock_id.is_(None),
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return await _resolve_and_apply(db, rows, scope=f"filer_id={filer_id}")


async def backfill_cusips_global(
    db: AsyncSession,
    limit: int = 10000,
) -> dict[str, int]:
    """Backfill all unmapped F13Holding rows across all filers (batched).

    The query is intentionally simple — ``WHERE stock_id IS NULL LIMIT N``.
    The partial index ``ix_f13_holdings_stock_id (… WHERE stock_id IS
    NOT NULL)`` does NOT help this scan, but for Phase 2 scale (<100k
    holdings) a sequential scan is acceptable.

    Args:
        db: AsyncSession — caller owns commit.
        limit: Max holdings to process this call.

    Returns:
        Same counter shape as :func:`backfill_cusips_for_filer`.
    """
    stmt = (
        select(
            F13Holding.id,
            F13Holding.cusip,
            F13Holding.name_of_issuer,
        )
        .where(F13Holding.stock_id.is_(None))
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return await _resolve_and_apply(db, rows, scope="global")


async def backfill_stocks_from_filings(
    db: AsyncSession,
) -> dict[str, int]:
    """Reverse direction: populate ``stocks.cusip`` from F13Holding rows.

    For each Stock with ``cusip IS NULL`` we look for one
    F13Holding mapped to that ``stock_id`` and copy its CUSIP onto the
    Stock row. This is what allows EXACT matching to start succeeding on
    subsequent backfill runs for the same issuer's other filings.

    A Stock may legitimately have multiple historical CUSIPs (mergers,
    corporate actions). Phase 2 takes the **first** mapped CUSIP observed
    — Phase 3 may add a per-stock CUSIP history table.

    Returns ``{stocks_updated}``.
    """
    # Find stocks lacking a CUSIP that have at least one mapped 13F holding.
    stmt = (
        select(F13Holding.stock_id, F13Holding.cusip)
        .join(Stock, Stock.id == F13Holding.stock_id)
        .where(
            F13Holding.stock_id.is_not(None),
            Stock.cusip.is_(None),
        )
        .distinct()
    )
    result = await db.execute(stmt)
    candidate_rows = result.all()

    # De-duplicate to one (stock_id, cusip) per stock — pick first seen.
    seen: dict[int, str] = {}
    for stock_id, cusip in candidate_rows:
        if stock_id is None or not cusip:
            continue
        sid = int(stock_id)
        if sid in seen:
            continue
        seen[sid] = cusip

    updated = 0
    for sid, cusip in seen.items():
        upd = (
            update(Stock)
            .where(Stock.id == sid, Stock.cusip.is_(None))
            .values(cusip=cusip)
        )
        res = await db.execute(upd)
        if res.rowcount:
            updated += 1

    logger.info(
        "cusip_backfill_stocks_done",
        stocks_updated=updated,
        candidates=len(seen),
    )
    return {"stocks_updated": updated}


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 — FIGI-aware variants
# ─────────────────────────────────────────────────────────────────────────


async def backfill_cusips_for_filer_with_figi(
    db: AsyncSession,
    filer_id: int,
    figi_client: OpenFigiClient | None = None,
    limit: int = 1000,
) -> dict[str, int]:
    """4-layer backfill for a single filer (EXACT / FIGI / NAME_LIKE / NONE).

    Same selection contract as :func:`backfill_cusips_for_filer` — only
    ``f13_holdings.stock_id IS NULL`` rows are considered. The difference
    is the resolver: this variant uses
    :func:`batch_resolve_cusips_with_figi`, which collects every EXACT
    miss into a single batched FIGI call (rate-limit-efficient).

    When ``figi_client`` is ``None``, this degrades gracefully to the
    Y3 3-layer strategy — caller logic stays the same.

    Returns ``{processed, exact_matches, figi_matches, fuzzy_matches,
    still_unmapped, upgraded}``.
    """
    stmt = (
        select(
            F13Holding.id,
            F13Holding.cusip,
            F13Holding.name_of_issuer,
        )
        .join(F13Filing, F13Filing.id == F13Holding.filing_id)
        .where(
            F13Filing.filer_id == filer_id,
            F13Holding.stock_id.is_(None),
        )
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return await _resolve_and_apply_with_figi(
        db, rows, scope=f"filer_id={filer_id}", figi_client=figi_client,
    )


async def backfill_cusips_global_with_figi(
    db: AsyncSession,
    figi_client: OpenFigiClient | None = None,
    limit: int = 10000,
) -> dict[str, int]:
    """4-layer global backfill — FIGI version of :func:`backfill_cusips_global`."""
    stmt = (
        select(
            F13Holding.id,
            F13Holding.cusip,
            F13Holding.name_of_issuer,
        )
        .where(F13Holding.stock_id.is_(None))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return await _resolve_and_apply_with_figi(
        db, rows, scope="global", figi_client=figi_client,
    )


# ─────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────


async def _resolve_and_apply(
    db: AsyncSession,
    rows: list,
    scope: str,
) -> dict[str, int]:
    """Common path for filer-scoped and global backfill.

    Resolves each ``(cusip, name_of_issuer)`` via ``batch_resolve_cusips``
    and emits UPDATE statements gated on ``stock_id IS NULL`` so a
    concurrent writer cannot silently lose data — if another process
    already mapped the row, our UPDATE no-ops via the WHERE clause.

    Also runs the EXACT-supersedes-NAME_LIKE upgrade as a separate pass
    (independently of the unmapped scan) so historical NAME_LIKE
    matches get promoted once ``stocks.cusip`` is populated.
    """
    pairs: list[tuple[str, str | None]] = [
        (r.cusip, r.name_of_issuer) for r in rows
    ]
    matches: list[CusipMatch] = await batch_resolve_cusips(db, pairs)

    exact_matches = 0
    fuzzy_matches = 0
    still_unmapped = 0
    processed = len(rows)

    for holding_row, match in zip(rows, matches):
        if match.stock_id is None:
            still_unmapped += 1
            continue
        # Guard with stock_id IS NULL so we never clobber a value set by
        # a parallel job — idempotent re-run safety.
        upd = (
            update(F13Holding)
            .where(
                F13Holding.id == holding_row.id,
                F13Holding.stock_id.is_(None),
            )
            .values(stock_id=match.stock_id)
        )
        res = await db.execute(upd)
        if not res.rowcount:
            # Concurrent writer beat us — treat as already-mapped.
            continue
        if match.match_confidence == _EXACT:
            exact_matches += 1
        elif match.match_confidence == _NAME_LIKE:
            fuzzy_matches += 1

    upgraded = await _upgrade_namelike_to_exact(db, scope=scope)

    out = {
        "processed": processed,
        "exact_matches": exact_matches,
        "fuzzy_matches": fuzzy_matches,
        "still_unmapped": still_unmapped,
        "upgraded": upgraded,
    }
    logger.info("cusip_backfill_batch_done", scope=scope, **out)
    return out


async def _resolve_and_apply_with_figi(
    db: AsyncSession,
    rows: list,
    scope: str,
    figi_client: OpenFigiClient | None,
) -> dict[str, int]:
    """FIGI-aware twin of :func:`_resolve_and_apply`.

    Routes through :func:`batch_resolve_cusips_with_figi` and tracks an
    additional ``figi_matches`` counter. UPDATE statements are still
    guarded by ``stock_id IS NULL`` so concurrent writers cannot clash.

    The upgrade-path pass (:func:`_upgrade_namelike_to_exact`) is reused
    unchanged — its semantics ("promote a holding when ``stocks.cusip``
    confirms an EXACT link") apply regardless of which layer first
    populated ``f13_holdings.stock_id``.
    """
    pairs: list[tuple[str, str | None]] = [
        (r.cusip, r.name_of_issuer) for r in rows
    ]
    matches: list[CusipMatchFigi] = await batch_resolve_cusips_with_figi(
        db, pairs, figi_client=figi_client,
    )

    exact_matches = 0
    figi_matches = 0
    fuzzy_matches = 0
    still_unmapped = 0
    processed = len(rows)

    for holding_row, match in zip(rows, matches):
        if match.stock_id is None:
            still_unmapped += 1
            continue
        upd = (
            update(F13Holding)
            .where(
                F13Holding.id == holding_row.id,
                F13Holding.stock_id.is_(None),
            )
            .values(stock_id=match.stock_id)
        )
        res = await db.execute(upd)
        if not res.rowcount:
            continue
        if match.match_confidence == _EXACT:
            exact_matches += 1
        elif match.match_confidence == _FIGI:
            figi_matches += 1
        elif match.match_confidence == _NAME_LIKE:
            fuzzy_matches += 1

    upgraded = await _upgrade_namelike_to_exact(db, scope=scope)

    out = {
        "processed": processed,
        "exact_matches": exact_matches,
        "figi_matches": figi_matches,
        "fuzzy_matches": fuzzy_matches,
        "still_unmapped": still_unmapped,
        "upgraded": upgraded,
    }
    logger.info("cusip_backfill_figi_batch_done", scope=scope, **out)
    return out


async def _upgrade_namelike_to_exact(
    db: AsyncSession,
    scope: str,
) -> int:
    """Promote holdings whose CUSIP now matches Stock.cusip exactly.

    Use case: a previous backfill linked a holding via NAME_LIKE while
    ``stocks.cusip`` was still NULL. Once ``backfill_stocks_from_filings``
    (or any other path) populates that Stock's CUSIP, future runs should
    re-link any other holdings of the same CUSIP via the more
    trustworthy EXACT layer, AND repoint holdings that were NAME_LIKE-
    mapped to a *different* Stock.

    Phase 2 keeps the scope conservative: we only flip a holding's
    ``stock_id`` when the existing Stock.cusip column carries the
    holding's CUSIP — i.e. confirm the link rather than reassign. This
    avoids the data-loss risk of a heuristic stealing a manually-mapped
    holding from one Stock to another mid-backfill.

    Returns the number of rows touched (always >=0).
    """
    # Holdings currently mapped to *some* Stock whose row carries a
    # DIFFERENT CUSIP than the holding (potential mismatch / stale name
    # fuzzy hit). We re-resolve EXACT and, if the EXACT layer agrees on
    # a different stock_id, swap.
    #
    # Phase 2 intentionally keeps this query side-effect-free unless we
    # find a CUSIP-confirmed correction — every UPDATE is guarded by an
    # EXACT match against ``stocks.cusip``.
    stmt = (
        select(
            F13Holding.id,
            F13Holding.cusip,
            F13Holding.stock_id,
            Stock.id.label("exact_stock_id"),
        )
        .join(Stock, Stock.cusip == F13Holding.cusip)
        .where(
            F13Holding.stock_id.is_not(None),
            F13Holding.stock_id != Stock.id,
        )
    )
    result = await db.execute(stmt)
    candidates = result.all()

    upgraded = 0
    for row in candidates:
        upd = (
            update(F13Holding)
            .where(F13Holding.id == row.id)
            .values(stock_id=int(row.exact_stock_id))
        )
        res = await db.execute(upd)
        if res.rowcount:
            upgraded += 1

    if upgraded:
        logger.info(
            "cusip_backfill_upgraded_namelike_to_exact",
            scope=scope,
            upgraded=upgraded,
        )
    return upgraded


# ─────────────────────────────────────────────────────────────────────────
# CLI entry point (`python -m app.services.institutional.cusip_backfill_job`)
# ─────────────────────────────────────────────────────────────────────────


async def _amain() -> None:
    """Module-as-script default: backfill globally with limit=10000."""
    from app.database import async_session  # local import — keeps tests light

    async with async_session() as db:
        out = await backfill_cusips_global(db)
        stocks_out = await backfill_stocks_from_filings(db)
        await db.commit()
        print({**out, **stocks_out})


if __name__ == "__main__":  # pragma: no cover - module-as-script
    import asyncio

    asyncio.run(_amain())
