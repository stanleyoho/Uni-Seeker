"""Run CUSIP backfill manually.

Phase 2 / UNI-F13-002 CLI wrapper around
``app.services.institutional.cusip_backfill_job``. Operators run this
after a 13F ingestion batch to map ``f13_holdings.stock_id`` against the
``stocks`` table, and optionally to reverse-populate ``stocks.cusip``.

Usage::

    cd backend && uv run python scripts/run_cusip_backfill.py --filer-id 42
    cd backend && uv run python scripts/run_cusip_backfill.py --global
    cd backend && uv run python scripts/run_cusip_backfill.py --global --update-stocks

The script owns its DB transaction — single commit at the end. On any
exception, the transaction is rolled back by the ``async with`` exit.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill F13Holding.stock_id via CUSIP / name matching."
    )
    parser.add_argument(
        "--filer-id",
        type=int,
        default=None,
        help="Restrict to one filer's holdings.",
    )
    parser.add_argument(
        "--global",
        action="store_true",
        dest="is_global",
        help="Scan all unmapped holdings across every filer.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Max holdings to process this run (default 10000).",
    )
    parser.add_argument(
        "--update-stocks",
        action="store_true",
        help="Also populate stocks.cusip from confirmed F13Holding mappings.",
    )
    args = parser.parse_args()

    # Lazy imports so --help works without bootstrapping the full app.
    from app.database import async_session
    from app.services.institutional.cusip_backfill_job import (
        backfill_cusips_for_filer,
        backfill_cusips_global,
        backfill_stocks_from_filings,
    )

    async with async_session() as db:
        if args.is_global:
            result: dict[str, object] = dict(
                await backfill_cusips_global(db, args.limit)
            )
        elif args.filer_id is not None:
            result = dict(
                await backfill_cusips_for_filer(db, args.filer_id, args.limit)
            )
        else:
            print("Specify --filer-id <id> or --global", file=sys.stderr)
            sys.exit(2)

        if args.update_stocks:
            stocks_result = await backfill_stocks_from_filings(db)
            result["stocks_updated"] = stocks_result.get("stocks_updated", 0)

        await db.commit()
        print(result)


if __name__ == "__main__":
    # Make `app` importable when run from repo root.
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, ".")
    asyncio.run(main())
