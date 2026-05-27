"""Add sync_states partial unique indexes

Revision ID: UNI_SYNC_001
Revises: UNI_USER_003
Create Date: 2026-05-27 19:30:00.000000

Backfill the partial unique indexes on `sync_states` that the codebase
has always assumed exist but no migration ever created:

  - `uq_sync_state_with_stock`  UNIQUE (dataset, stock_id) WHERE stock_id IS NOT NULL
  - `uq_sync_state_global`      UNIQUE (dataset)           WHERE stock_id IS NULL

Discovered 2026-05-27 during a cross-repo audit: the model file
`app/models/sync_state.py` had a comment claiming the partial indexes
were "created via migration", but no such migration existed. The
production PG instance therefore lacked both indexes, and the sync
tasks' `INSERT ... ON CONFLICT ON CONSTRAINT uq_sync_state_with_stock`
failed with `UndefinedObjectError: constraint does not exist`.

That silent-fail caused the margin / revenue / per_pbr sync tasks to
do zero work on every run for the past ~27 days while the `prices`
sync (which doesn't depend on those constraints in the same way and
was earlier in the canonical task order) kept running.

The companion code change also updates the `on_conflict_do_update`
calls from `constraint=...` to `index_elements + index_where`, since
PG partial unique indexes are matched by ON CONFLICT (cols) WHERE,
not by ON CONFLICT ON CONSTRAINT.

Idempotent: uses CREATE UNIQUE INDEX IF NOT EXISTS so re-applying on
local dev DBs that received the manual emergency fix on 2026-05-27
is safe.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "UNI_SYNC_001"
down_revision: str | None = "UNI_USER_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_state_with_stock "
        "ON sync_states (dataset, stock_id) WHERE stock_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_state_global "
        "ON sync_states (dataset) WHERE stock_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sync_state_global")
    op.execute("DROP INDEX IF EXISTS uq_sync_state_with_stock")
