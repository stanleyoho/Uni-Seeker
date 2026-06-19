"""Add f13_filings covering index + backfill sync_states partial unique indexes.

Revision ID: UNI_PERF_002
Revises: 3bcd5668fe84
Create Date: 2026-06-20

Two index gaps surfaced by the 2026-06 prediction-store / index audit:

1. ``f13_filings`` covering index ``(filer_id, report_period_end DESC, id)``
   ----------------------------------------------------------------------
   The "latest filing per filer" read path (filing_repo / filing_service)
   orders by ``report_period_end DESC`` scoped to a ``filer_id`` and then
   joins/returns ``id``. The existing ``ix_f13_filings_filer_period_desc``
   index is ``(filer_id, report_period_end DESC)`` — Postgres still has to
   visit the heap to fetch ``id``. Appending ``id`` as a trailing index
   column makes the hot lookup index-only (covering), eliminating the heap
   fetch on the per-filer latest-period scan.

   This is ADDITIVE: the original 2-col index is kept (it remains the
   correct, smaller index for ``WHERE filer_id = ? ORDER BY
   report_period_end DESC`` when ``id`` isn't projected, and the model
   declaration in ``app/db/models/institutional/filing.py`` still owns it).

2. ``sync_states`` partial unique indexes — idempotent backfill
   ----------------------------------------------------------------------
   ``uq_sync_state_with_stock``  UNIQUE (dataset, stock_id) WHERE stock_id IS NOT NULL
   ``uq_sync_state_global``      UNIQUE (dataset)           WHERE stock_id IS NULL

   These were already created by ``UNI-SYNC-001``. This migration re-asserts
   them with ``CREATE UNIQUE INDEX IF NOT EXISTS`` so they are guaranteed
   present on any DB that (for whatever reason) is missing them, while being
   a safe no-op on every DB that already has them. The audit asked for them
   "if not already present" — IF NOT EXISTS encodes exactly that.

Portability
===========
All four statements use raw ``CREATE [UNIQUE] INDEX IF NOT EXISTS`` SQL so
re-applying is idempotent on Postgres. SQLite (used only by the fast unit
suite, which builds schema via ``Base.metadata.create_all`` and does NOT run
this migration) also understands ``IF NOT EXISTS`` and a trailing-column /
DESC index, so the migration stays valid under both dialects for the
pg_integration gate and any future sqlite-backed migration test.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "UNI_PERF_002"
down_revision: str | None = "3bcd5668fe84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Index name constants — module scope keeps upgrade/downgrade in sync and
# greppable (cf. UNI-PERF-001 convention).
IX_F13_FILINGS_FILER_PERIOD_ID = "ix_f13_filings_filer_period_id_covering"
UQ_SYNC_STATE_WITH_STOCK = "uq_sync_state_with_stock"
UQ_SYNC_STATE_GLOBAL = "uq_sync_state_global"


def upgrade() -> None:
    # 1. f13_filings covering index: (filer_id, report_period_end DESC, id).
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {IX_F13_FILINGS_FILER_PERIOD_ID} "
        "ON f13_filings (filer_id, report_period_end DESC, id)"
    )

    # 2. sync_states partial unique indexes — idempotent backfill
    #    ("if not already present"). No-op where UNI-SYNC-001 already created
    #    them.
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {UQ_SYNC_STATE_WITH_STOCK} "
        "ON sync_states (dataset, stock_id) WHERE stock_id IS NOT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {UQ_SYNC_STATE_GLOBAL} "
        "ON sync_states (dataset) WHERE stock_id IS NULL"
    )


def downgrade() -> None:
    # Only drop the covering index this migration introduced. The two
    # sync_states partial unique indexes are OWNED by UNI-SYNC-001 — dropping
    # them here would corrupt that migration's contract, so we deliberately
    # leave them (this migration's upgrade was an idempotent no-op for them).
    op.execute(f"DROP INDEX IF EXISTS {IX_F13_FILINGS_FILER_PERIOD_ID}")
