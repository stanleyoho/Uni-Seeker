"""Add notify_via_email to users (Email notification channel).

Revision ID: UNI_USER_003
Revises: UNI_ALERT_001
Create Date: 2026-05-19

Adds an opt-in boolean column so the per-user notification dispatcher
can fan out 13F + alert-rule notifications to email in addition to (or
instead of) Telegram. Defaults to ``FALSE`` so existing users are NOT
opted in implicitly — sending unsolicited email after a passive schema
migration would be a compliance smell.

We reuse ``users.email`` (already unique + NOT NULL) as the destination
address rather than adding a second ``notification_email`` column. The
trade-off: a user who wants notifications to a different mailbox than
their login email needs to change their primary email. That is the rare
case; modelling it now would add a second uniqueness constraint and a
verification flow we do not have infrastructure for in Round 14.

Why not a JSONB ``notification_preferences`` column (forward-compatible
shape)? Two reasons:
  1. Today's surface is two booleans (TG + email). JSONB pays an
     indexing + validation cost that two columns avoid.
  2. The schema already shipped ``telegram_chat_id`` as a column in
     UNI_F13_002; a JSONB rewrite would be a breaking migration for
     all existing per-user TG bindings.

Phase-2 (LINE / Webhook) will revisit consolidation when the channel
list outgrows columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_USER_003"
# Merge migration — collapses the two open heads that existed before
# this commit:
#   * UNI_F13_002 (telegram_chat_id column)
#   * UNI_ALERT_001 (alert_rules table)
# Both branches descend from UNI_PORT_003. We list both as parents so
# alembic linearises the graph at this point and downstream migrations
# only have to chase a single head again.
down_revision: str | Sequence[str] | None = (
    "UNI_F13_002",
    "UNI_ALERT_001",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_via_email",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_via_email")
