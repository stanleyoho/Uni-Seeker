"""Add 13F Holdings Tracker tables — Institutional Phase 1 / UNI-F13-001.

Revision ID: UNI_F13_001
Revises: UNI_PORT_003
Create Date: 2026-05-22

Creates the four Phase 1 tables for the 13F Holdings Tracker module
(design doc §4 Tables 1-4):
  - f13_filers              — shared filer identity (no user_id)
  - f13_user_subscriptions  — user watchlist of filers
  - f13_filings             — quarterly 13F-HR snapshot meta
  - f13_holdings            — per-position rows inside a filing

Plus a schema patch to `stocks` adding `cusip VARCHAR(9)` (nullable;
not back-filled — Phase 1 lazy lookup tolerates NULL). Index is partial
on Postgres (WHERE cusip IS NOT NULL) for fast CUSIP → stock lookup;
SQLite ignores the WHERE clause but still benefits from the index.

Decisions baked in (per Stanley):
  Q1  on-demand only — no scheduled job in Phase 1 (no extra table)
  Q2  f13_filers shared — NO user_id column
  Q3  AUM display = total_value_usd + options_notional_usd (both cols)
  Q5  tier limits enforced in service layer, not DB
  Q8  backfill 4 quarters handled by Batch A2 ingester, not migration
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "UNI_F13_001"
down_revision: Union[str, None] = "UNI_PORT_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── f13_filers ────────────────────────────────────────────────────────
    op.create_table(
        "f13_filers",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=500), nullable=True),
        sa.Column(
            "latest_total_value_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "latest_options_notional_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column("latest_filing_date", sa.Date(), nullable=True),
        sa.Column("latest_position_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("cik", name="uq_f13_filers_cik"),
    )
    op.create_index("ix_f13_filers_cik", "f13_filers", ["cik"])
    op.create_index("ix_f13_filers_name", "f13_filers", ["name"])

    # ── f13_user_subscriptions ────────────────────────────────────────────
    op.create_table(
        "f13_user_subscriptions",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column(
            "user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "filer_id", sa.BigInteger,
            sa.ForeignKey("f13_filers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscribed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "notify_on_new_filing", sa.Boolean(),
            nullable=False, server_default=sa.true(),
        ),
        sa.UniqueConstraint(
            "user_id", "filer_id",
            name="uq_f13_user_subscriptions_user_filer",
        ),
    )
    op.create_index(
        "ix_f13_user_subscriptions_user_id",
        "f13_user_subscriptions",
        ["user_id"],
    )
    op.create_index(
        "ix_f13_user_subscriptions_filer_id",
        "f13_user_subscriptions",
        ["filer_id"],
    )

    # ── f13_filings ───────────────────────────────────────────────────────
    op.create_table(
        "f13_filings",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column(
            "filer_id", sa.BigInteger,
            sa.ForeignKey("f13_filers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("form_type", sa.String(length=20), nullable=False),
        sa.Column("report_period_end", sa.Date(), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "total_value_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column(
            "options_notional_usd",
            sa.Numeric(precision=24, scale=2),
            nullable=True,
        ),
        sa.Column("total_positions", sa.Integer(), nullable=True),
        sa.Column("raw_xml_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "filer_id", "accession_number",
            name="uq_f13_filings_filer_accession",
        ),
        sa.CheckConstraint(
            "form_type IN ('13F-HR', '13F-HR/A')",
            name="ck_f13_filings_form_type_valid",
        ),
    )
    op.create_index(
        "ix_f13_filings_filer_period_desc",
        "f13_filings",
        ["filer_id", sa.text("report_period_end DESC")],
    )
    op.create_index(
        "ix_f13_filings_filer_filed_desc",
        "f13_filings",
        ["filer_id", sa.text("filed_at DESC")],
    )

    # ── f13_holdings ──────────────────────────────────────────────────────
    op.create_table(
        "f13_holdings",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column(
            "filing_id", sa.BigInteger,
            sa.ForeignKey("f13_filings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cusip", sa.String(length=9), nullable=False),
        sa.Column("name_of_issuer", sa.String(length=255), nullable=False),
        sa.Column(
            "value_usd", sa.Numeric(precision=24, scale=2), nullable=False,
        ),
        sa.Column(
            "shares", sa.Numeric(precision=24, scale=0), nullable=True,
        ),
        sa.Column("put_call", sa.String(length=10), nullable=True),
        sa.Column(
            "investment_discretion", sa.String(length=20), nullable=True,
        ),
        sa.Column(
            "voting_authority_sole",
            sa.Numeric(precision=24, scale=0),
            nullable=True,
        ),
        sa.Column(
            "voting_authority_shared",
            sa.Numeric(precision=24, scale=0),
            nullable=True,
        ),
        sa.Column(
            "voting_authority_none",
            sa.Numeric(precision=24, scale=0),
            nullable=True,
        ),
        sa.Column(
            "stock_id", sa.BigInteger,
            sa.ForeignKey("stocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "put_call IS NULL OR put_call IN ('PUT', 'CALL')",
            name="ck_f13_holdings_put_call_valid",
        ),
    )
    op.create_index("ix_f13_holdings_filing_id", "f13_holdings", ["filing_id"])
    op.create_index("ix_f13_holdings_cusip", "f13_holdings", ["cusip"])
    # Partial index — only rows with a mapped stock_id participate in
    # cross-filer "who else holds AAPL" lookups. SQLite ignores
    # postgresql_where and falls back to a plain index, which is fine.
    op.create_index(
        "ix_f13_holdings_stock_id",
        "f13_holdings",
        ["stock_id"],
        postgresql_where=sa.text("stock_id IS NOT NULL"),
    )

    # ── stocks.cusip patch ────────────────────────────────────────────────
    # Universal identifier shared by Portfolio / Watchlist / 13F modules.
    # Nullable: not all stocks have a CUSIP (TW listings, ETF variants).
    op.add_column(
        "stocks",
        sa.Column("cusip", sa.String(length=9), nullable=True),
    )
    op.create_index(
        "ix_stocks_cusip",
        "stocks",
        ["cusip"],
        unique=True,
        postgresql_where=sa.text("cusip IS NOT NULL"),
    )


def downgrade() -> None:
    # Reverse FK order: holdings → filings → user_subscriptions → filers
    # Then drop stocks.cusip last (it's referenced by holdings.stock_id
    # FK but only as the target column id, not cusip, so order is safe).
    op.drop_index("ix_stocks_cusip", table_name="stocks")
    op.drop_column("stocks", "cusip")

    op.drop_index("ix_f13_holdings_stock_id", table_name="f13_holdings")
    op.drop_index("ix_f13_holdings_cusip", table_name="f13_holdings")
    op.drop_index("ix_f13_holdings_filing_id", table_name="f13_holdings")
    op.drop_table("f13_holdings")

    op.drop_index(
        "ix_f13_filings_filer_filed_desc", table_name="f13_filings",
    )
    op.drop_index(
        "ix_f13_filings_filer_period_desc", table_name="f13_filings",
    )
    op.drop_table("f13_filings")

    op.drop_index(
        "ix_f13_user_subscriptions_filer_id",
        table_name="f13_user_subscriptions",
    )
    op.drop_index(
        "ix_f13_user_subscriptions_user_id",
        table_name="f13_user_subscriptions",
    )
    op.drop_table("f13_user_subscriptions")

    op.drop_index("ix_f13_filers_name", table_name="f13_filers")
    op.drop_index("ix_f13_filers_cik", table_name="f13_filers")
    op.drop_table("f13_filers")
