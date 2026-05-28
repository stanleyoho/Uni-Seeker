"""Expand sync_states.error_message column 500 -> 2000

Revision ID: UNI_SYNC_002
Revises: UNI_SYNC_001
Create Date: 2026-05-29 00:00:00.000000

PR #92 added a hardened except block that writes `error_message` on any
sync_task failure. The column was sized `VARCHAR(500)`, which is too short
for a typical Python traceback. The PR #92 sub-agent caught this during
testing: a `traceback.format_exc()[:500]` truncation drops the exception
class line (which is the last line of a traceback), making the
`error_message` useless for triage.

That PR shipped a workaround (prepend `"{ExceptionClass}: {msg}\\n"` so the
class survives the cut), but the root cause is the column ceiling. This
migration raises the ceiling to 2000 chars, enough to keep the exception
class line, the message, and a useful tail of the traceback.

The downgrade narrows back to 500. PG will refuse to alter to a narrower
type if any existing row exceeds it, which is the desired fail-fast: if
prod has rows with >500 chars, downgrade should surface that explicitly
rather than silently truncating data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_SYNC_002"
down_revision: str | None = "UNI_SYNC_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "sync_states",
        "error_message",
        type_=sa.String(2000),
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sync_states",
        "error_message",
        type_=sa.String(500),
        existing_type=sa.String(2000),
        existing_nullable=True,
    )
