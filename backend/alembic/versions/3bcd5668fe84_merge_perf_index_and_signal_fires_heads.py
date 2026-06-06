"""merge perf-index and signal_fires heads into a single linear head

Revision ID: 3bcd5668fe84
Revises: UNI_PERF_001, UNI_SIGFIRE_001
Create Date: 2026-06-06

The migration DAG had two divergent heads:

  - ``UNI_PERF_001`` (index_gaps) descends from ``UNI_SYNC_002``.
  - ``UNI_SIGFIRE_001`` (add_signal_fires) descends from
    ``UNI_TWINST_001`` which also descends from ``UNI_SYNC_002``.

With two heads ``alembic upgrade head`` fails outright with
"Multiple head revisions are present for given argument 'head'". This is a
no-op merge revision: both branches are independent (one adds indexes, one
adds the ``signal_fires`` table), so unifying them requires no DDL — it only
collapses the DAG back to a single head so ``upgrade head`` resolves.

This merge is safe on every DB state: it touches no tables, and stamping
through it (the path ``init_fresh_db.py`` takes via ``alembic stamp head``)
simply records the merged revision in ``alembic_version``.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "3bcd5668fe84"
down_revision: str | Sequence[str] | None = ("UNI_PERF_001", "UNI_SIGFIRE_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: this revision only merges two divergent heads."""


def downgrade() -> None:
    """No-op: splitting back into two heads requires no DDL."""
