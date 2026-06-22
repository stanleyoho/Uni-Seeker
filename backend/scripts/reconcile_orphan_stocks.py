"""One-off reconciliation: fold mis-suffixed orphan `stocks` rows into their
canonical twin, then soft-delete the orphans.

Background: a historical stock_info bug stored TPEX stocks under `.TW` (and a
few uplisted TWSE stocks under `.TWO`). The sync fix (commit fa4d48c) now writes
each stock under its canonical symbol derived from the live FinMind feed, which
leaves the old mis-suffixed rows orphaned — and they hold the bulk of the price
history. This script repoints every child-table row from the orphan stock id to
its canonical twin (conflict-safe: move non-colliding rows, drop the few that
collide on the natural key because the canonical row already has them), then
sets the orphan `stocks.is_active = false` (soft-delete, reversible — we do NOT
hard-delete).

Canonical map is read from a JSON file (stock_id -> canonical symbol) produced
from the live feed. DB URL comes from UNI_DATABASE_URL (so it can run against a
scratch clone first). Idempotent: re-running finds no orphans / no work.

Child tables repointed (natural key for the collision guard):
  stock_prices    (stock_id, date)
  margin_trading  (stock_id, date)
  price_estimates (stock_id, date, model_type)
  sync_states     (dataset, stock_id)
All other stocks-FK tables were verified to have 0 orphan references.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CANON_PATH = os.environ.get("CANON_MAP", "/tmp/canon_map.json")

# child table -> the natural-key columns OTHER than stock_id (collision guard)
CHILD_TABLES = {
    "stock_prices": ["date"],
    "margin_trading": ["date"],
    "price_estimates": ["date", "model_type"],
    "sync_states": ["dataset"],
}


async def main(apply: bool) -> None:
    url = os.environ["UNI_DATABASE_URL"]
    if "scratch" not in url and not apply:
        pass  # dry-run on any DB is fine
    canon = json.load(open(CANON_PATH))  # stock_id -> canonical symbol
    engine = create_async_engine(url)
    async with engine.begin() as c:
        # 1. Build orphan -> canonical id mapping in a temp table.
        rows = (await c.execute(text("SELECT id, symbol, is_active FROM stocks"))).all()
        by_symbol = {r.symbol: r.id for r in rows}
        mapping = []  # (orphan_id, canon_id)
        for r in rows:
            sid = r.symbol.split(".")[0]
            target = canon.get(sid)
            # Only ACTIVE orphans need work; already soft-deleted ones are done
            # (keeps re-runs cleanly idempotent — reports 0).
            if target and r.symbol != target and target in by_symbol and r.is_active:
                mapping.append((r.id, by_symbol[target]))
        print(f"orphans with an existing canonical twin: {len(mapping)}")
        if not mapping:
            print("nothing to reconcile.")
            await engine.dispose()
            return

        await c.execute(text("CREATE TEMP TABLE _omap (orphan_id int PRIMARY KEY, canon_id int) ON COMMIT DROP"))
        await c.execute(
            text("INSERT INTO _omap (orphan_id, canon_id) VALUES (:o, :c)"),
            [{"o": o, "c": cc} for o, cc in mapping],
        )

        # 2. Repoint each child table: move non-colliding rows, delete collisions.
        for tbl, keys in CHILD_TABLES.items():
            # collision = a canonical-id row already shares the natural key
            key_match = " AND ".join(f"x.{k} = t.{k}" for k in keys)
            moved = (await c.execute(text(f"""
                UPDATE {tbl} t SET stock_id = m.canon_id
                FROM _omap m
                WHERE t.stock_id = m.orphan_id
                  AND NOT EXISTS (
                    SELECT 1 FROM {tbl} x
                    WHERE x.stock_id = m.canon_id AND {key_match}
                  )
            """))).rowcount
            dropped = (await c.execute(text(f"""
                DELETE FROM {tbl} t USING _omap m WHERE t.stock_id = m.orphan_id
            """))).rowcount
            print(f"  {tbl}: moved={moved} dropped_dupes={dropped}")

        # 3. Soft-delete the orphan stock rows (reversible).
        deact = (await c.execute(text("""
            UPDATE stocks s SET is_active = false
            FROM _omap m WHERE s.id = m.orphan_id AND s.is_active
        """))).rowcount
        print(f"  stocks soft-deleted (is_active=false): {deact}")

        if not apply:
            print("DRY-RUN: rolling back.")
            raise _Rollback()
    await engine.dispose()


class _Rollback(Exception):
    pass


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    try:
        asyncio.run(main(apply))
        print("APPLIED." if apply else "dry-run complete.")
    except _Rollback:
        print("dry-run complete (rolled back).")
