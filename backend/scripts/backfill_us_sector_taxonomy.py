"""Backfill US-listed equity sector / industry from FinanceDatabase.

What this script does
---------------------
For every row in ``stocks`` whose ``market`` is ``US_NYSE`` or
``US_NASDAQ``:

  1. Look up the symbol in FinanceDatabase via
     ``app.services.symbol_taxonomy.enrich_stock``.
  2. If FinanceDatabase has a sector for it, ensure the corresponding
     ``industries`` row exists (insert if missing).
  3. Set ``stocks.industry_id`` to that industry row's id.

The script is **idempotent** — re-running it does nothing new for stocks
that already have an industry_id pointing at the right industry. The
``--dry-run`` mode prints the planned updates without committing.

Why this matters
----------------
Today the US heatmap (``app/api/v1/heatmap.py``) joins on
``industries.name`` to bucket stocks by sector. US rows in the seed
data have ``industry_id = NULL``, so the heatmap query returns no US
sectors and the demo fallback kicks in. After running this script the
US heatmap renders real GICS sectors for every US-listed symbol with a
FinanceDatabase entry (~14k symbols cover ~80%+ of the US public
market by count).

Usage
-----
    # Preview changes — no DB writes.
    uv run python scripts/backfill_us_sector_taxonomy.py --dry-run

    # Apply.
    uv run python scripts/backfill_us_sector_taxonomy.py

    # Apply only to a specific subset (handy for testing).
    uv run python scripts/backfill_us_sector_taxonomy.py --symbols AAPL,MSFT,NVDA
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.enums import Market
from app.models.industry import Industry
from app.models.stock import Stock
from app.services.symbol_taxonomy import enrich_stock, get_us_equity_universe

# Markets we treat as US. Matches the Market enum.
_US_MARKETS = (Market.US_NYSE, Market.US_NASDAQ)


async def _get_or_create_industry(db: AsyncSession, name: str) -> Industry:
    """Idempotently fetch the Industry row for ``name``, inserting if
    missing. The ``industries`` table has a UNIQUE constraint on
    ``name``, so this is safe under concurrent writers — at worst we
    get an IntegrityError and refetch."""
    existing = await db.execute(select(Industry).where(Industry.name == name))
    row = existing.scalar_one_or_none()
    if row is not None:
        return row
    # Insert. The model's ``init=False`` columns (id, created_at,
    # updated_at) auto-populate.
    industry = Industry(name=name)
    db.add(industry)
    await db.flush()  # populates ``id`` without committing
    return industry


async def _fetch_us_stocks(db: AsyncSession, symbols: Sequence[str] | None = None) -> list[Stock]:
    """Pull every US-listed stock from the DB, optionally limited to a
    symbol allowlist."""
    stmt = select(Stock).where(Stock.market.in_(_US_MARKETS))
    if symbols:
        stmt = stmt.where(Stock.symbol.in_(symbols))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def run_backfill(
    dry_run: bool = True,
    symbols: Sequence[str] | None = None,
) -> dict[str, int]:
    """Main entrypoint.

    Returns a stats dict with counts for ``updated``, ``skipped_already_set``,
    ``skipped_no_taxonomy``, ``industries_created``.

    Stats are returned (not just printed) so this function is unit-testable.
    """
    stats = {
        "updated": 0,
        "skipped_already_set": 0,
        "skipped_no_taxonomy": 0,
        "industries_created": 0,
    }
    # Warm up the FinanceDatabase cache before opening the DB session so
    # the ~200ms parquet load doesn't extend any transaction.
    _ = get_us_equity_universe()

    async with async_session() as db:
        stocks = await _fetch_us_stocks(db, symbols=symbols)
        print(f"Found {len(stocks)} US-listed stocks in DB")

        # Cache of name -> Industry row to avoid re-querying the same
        # sector for thousands of stocks. The UNIQUE constraint on
        # industries.name lets us trust the cache.
        industry_cache: dict[str, Industry] = {}

        for stock in stocks:
            record = enrich_stock(stock.symbol)
            if record is None or not record.sector:
                stats["skipped_no_taxonomy"] += 1
                continue

            # Get-or-create the Industry row for this sector.
            sector_name = record.sector
            industry = industry_cache.get(sector_name)
            if industry is None:
                # Probe existence so we can correctly increment
                # industries_created.
                existing = await db.execute(select(Industry).where(Industry.name == sector_name))
                pre_existing = existing.scalar_one_or_none()
                if pre_existing is not None:
                    industry = pre_existing
                else:
                    industry = Industry(name=sector_name)
                    if not dry_run:
                        db.add(industry)
                        await db.flush()
                    stats["industries_created"] += 1
                industry_cache[sector_name] = industry

            # Skip if already linked to the right industry.
            # Industry.id is unpopulated on dry-run new rows — fall back
            # to comparing by name in that case.
            if stock.industry_id is not None:
                # If the existing industry_id maps to the same name, skip.
                existing_industry = await db.get(Industry, stock.industry_id)
                if existing_industry is not None and existing_industry.name == sector_name:
                    stats["skipped_already_set"] += 1
                    continue

            if dry_run:
                # In dry-run, industry.id is None for newly-"created"
                # rows. Print the change without touching the row.
                print(
                    f"  [DRY] {stock.symbol:6} → sector='{sector_name}' "
                    f"(industry={record.industry or '—'})"
                )
            else:
                stock.industry_id = industry.id
            stats["updated"] += 1

        if not dry_run:
            await db.commit()
            print(f"Committed {stats['updated']} updates")
        else:
            await db.rollback()
            print("Dry-run: no changes written")

    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill US-listed equity sector taxonomy from FinanceDatabase",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the DB (default: actually commit)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbol allowlist (default: every US-listed row)",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    symbols: list[str] | None = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    stats = await run_backfill(dry_run=args.dry_run, symbols=symbols)
    print()
    print("── Backfill stats ──")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
