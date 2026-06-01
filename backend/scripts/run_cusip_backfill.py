"""Run CUSIP backfill manually.

Phase 2 / UNI-F13-002 (3-layer) — Phase 3 / UNI-F13-003 (4-layer with FIGI).

CLI wrapper around ``app.services.institutional.cusip_backfill_job``.
Operators run this after a 13F ingestion batch to map
``f13_holdings.stock_id`` against the ``stocks`` table, and optionally to
reverse-populate ``stocks.cusip``.

Usage::

    cd backend && uv run python scripts/run_cusip_backfill.py --filer-id 42
    cd backend && uv run python scripts/run_cusip_backfill.py --global
    cd backend && uv run python scripts/run_cusip_backfill.py --global --update-stocks
    cd backend && uv run python scripts/run_cusip_backfill.py --global --use-figi

With ``--use-figi``, the resolver reads ``OPENFIGI_API_KEY`` (raw name) or
``UNI_OPENFIGI_API_KEY`` from env. Missing → free tier (25 req/min). The
flag is opt-in so existing automation continues to run the Y3 3-layer
path unchanged.

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
    parser.add_argument(
        "--use-figi",
        action="store_true",
        help=(
            "Enable OpenFIGI layer 2 (CUSIP -> ticker). Reads "
            "OPENFIGI_API_KEY / UNI_OPENFIGI_API_KEY from env; missing -> "
            "free tier (25 req/min). Without this flag the Y3 3-layer "
            "strategy runs unchanged."
        ),
    )
    args = parser.parse_args()

    # Lazy imports so --help works without bootstrapping the full app.
    from app.database import async_session
    from app.services.institutional.cusip_backfill_job import (
        backfill_cusips_for_filer,
        backfill_cusips_for_filer_with_figi,
        backfill_cusips_global,
        backfill_cusips_global_with_figi,
        backfill_stocks_from_filings,
    )

    figi_ctx = None
    if args.use_figi:
        from app.modules.institutional.openfigi_client import (
            OpenFigiClient,
            openfigi_api_key_from_env,
        )

        figi_ctx = OpenFigiClient(api_key=openfigi_api_key_from_env())

    async with async_session() as db:

        async def _do_backfill() -> dict[str, object]:
            if args.is_global:
                if args.use_figi:
                    return dict(
                        await backfill_cusips_global_with_figi(
                            db,
                            figi_client=figi_ctx,
                            limit=args.limit,
                        )
                    )
                return dict(await backfill_cusips_global(db, args.limit))
            if args.filer_id is not None:
                if args.use_figi:
                    return dict(
                        await backfill_cusips_for_filer_with_figi(
                            db,
                            args.filer_id,
                            figi_client=figi_ctx,
                            limit=args.limit,
                        )
                    )
                return dict(await backfill_cusips_for_filer(db, args.filer_id, args.limit))
            print("Specify --filer-id <id> or --global", file=sys.stderr)
            sys.exit(2)

        if figi_ctx is not None:
            async with figi_ctx:
                result = await _do_backfill()
        else:
            result = await _do_backfill()

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
