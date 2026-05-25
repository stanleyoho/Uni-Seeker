"""Add alert_rules table — User-Defined Alert Rules.

Revision ID: UNI_ALERT_001
Revises: UNI_PORT_003
Create Date: 2026-05-19

Spec: 2026-05-19 user-defined alert rules + TG notification.

Schema rationale
----------------
One row per (user, rule). The rule can target a specific
(symbol, market) tuple (POSITION_*) or be portfolio-wide
(PORTFOLIO_*). symbol/market are nullable for portfolio-wide rules.

threshold_value is intentionally NUMERIC(24,8) — the same precision
used everywhere else for prices and totals so PCT vs ABSOLUTE rules
both fit cleanly without coercion.

Status lifecycle:
  ACTIVE  → user wants this rule evaluated each tick.
  TRIGGERED → fired; rule is paused until user re-enables (this avoids
              spamming when the price hovers around the threshold).
  PAUSED  → user manually paused.

Indices: (user_id, status) is the hot path for the scheduler
("give me every active rule for this user"); a single B-tree on
status alone would not be selective enough at scale.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_ALERT_001"
down_revision: str | None = "UNI_PORT_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RULE_TYPES = (
    "POSITION_PRICE_DROP",
    "POSITION_PRICE_RISE",
    "PORTFOLIO_VALUE_ABOVE",
    "PORTFOLIO_VALUE_BELOW",
    "POSITION_PNL_PCT_ABOVE",
    "POSITION_PNL_PCT_BELOW",
)
_STATUSES = ("ACTIVE", "PAUSED", "TRIGGERED")
_THRESHOLD_TYPES = ("PCT", "ABSOLUTE")


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column(
            "user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rule_type", sa.String(length=30), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("market", sa.String(length=20), nullable=True),
        sa.Column(
            "threshold_value", sa.Numeric(precision=24, scale=8), nullable=False,
        ),
        sa.Column("threshold_type", sa.String(length=10), nullable=False),
        sa.Column(
            "status", sa.String(length=10),
            nullable=False, server_default="ACTIVE",
        ),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "rule_type IN ("
            + ", ".join(f"'{rt}'" for rt in _RULE_TYPES)
            + ")",
            name="ck_alert_rules_rule_type",
        ),
        sa.CheckConstraint(
            "status IN ("
            + ", ".join(f"'{s}'" for s in _STATUSES)
            + ")",
            name="ck_alert_rules_status",
        ),
        sa.CheckConstraint(
            "threshold_type IN ("
            + ", ".join(f"'{t}'" for t in _THRESHOLD_TYPES)
            + ")",
            name="ck_alert_rules_threshold_type",
        ),
        # Position-scoped rules need both symbol + market; portfolio-wide
        # rules need neither. The XOR guarantees consistency at the DB
        # layer so a malformed service write cannot land.
        sa.CheckConstraint(
            "("
            "  rule_type LIKE 'POSITION_%' AND symbol IS NOT NULL "
            "  AND market IS NOT NULL"
            ") OR ("
            "  rule_type LIKE 'PORTFOLIO_%' AND symbol IS NULL "
            "  AND market IS NULL"
            ")",
            name="ck_alert_rules_scope_consistency",
        ),
    )
    op.create_index(
        "ix_alert_rules_user_status",
        "alert_rules",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_alert_rules_user_id",
        "alert_rules",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_user_status", table_name="alert_rules")
    op.drop_table("alert_rules")
