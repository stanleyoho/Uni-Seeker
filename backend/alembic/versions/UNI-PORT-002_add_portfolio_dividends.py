"""Add portfolio_dividends table — Portfolio Tracker Phase 2.

Revision ID: UNI_PORT_002
Revises: UNI_PORT_001
Create Date: 2026-05-19

Adds the `portfolio_dividends` table promised by design doc §6.2 Table 5
(originally tagged Phase 3, pulled into Phase 2 batch A1 per current
rollout plan).

Schema deviations from spec §6.2 Table 5
-----------------------------------------
spec lists only 7 columns (id / account_id / symbol / ex_date /
amount_per_share / kind / created_at). For a production-ready table the
Phase 2 plan needs additional fields:

  - `market` (Market enum)            — multi-market portfolios need it
                                         alongside symbol (mirrors
                                         portfolio_trades shape)
  - `dividend_type` (renamed `kind`)  — kept String(10) with CHECK as
                                         spec suggested (no new PG ENUM
                                         to avoid namespace creep)
  - `ex_dividend_date` (renamed       — clearer than spec's `ex_date`
     from spec's `ex_date`)
  - `pay_date` (Date, nullable)        — actual cash-paid date
  - `quantity_at_record` (Numeric)     — shares held on record date
                                         (drives total_amount calc)
  - `currency` (String(3), default     — match account currency at
     "TWD")                              record time (immutable)
  - `withholding_tax` (Numeric,        — TW 二代健保補充保費 / US 30 %
     default 0)                          NRA withholding
  - `note` (String, nullable)          — free-form ops note
  - `updated_at` (DateTime tz)         — onupdate=now() — matches trades

`total_amount` / `net_amount` are NOT stored — they are derived
(amount_per_share × quantity_at_record − withholding_tax) and the
service layer computes them. Stored derived columns would split between
SQLite test runs and Postgres prod (SQLite lacks GENERATED ALWAYS AS
parity with Postgres for our Decimal precision).

Indices
-------
- `(account_id, ex_dividend_date)` descending implied via query —
  Postgres uses btree which is order-agnostic for single-key range
  scans; we don't bother with explicit DESC.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

from alembic import op

revision: str = "UNI_PORT_002"
down_revision: str | None = "UNI_PORT_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Reuse the existing `market_enum` Postgres type (created by the 3NF
# schema migration and shared with stocks / portfolio_accounts / trades
# / lots / positions). create_type=False so upgrade does NOT CREATE TYPE
# a second time, and downgrade does NOT DROP it — other tables depend
# on it.
def _market_enum() -> PgEnum:
    return PgEnum(
        "TW_TWSE",
        "TW_TPEX",
        "US_NYSE",
        "US_NASDAQ",
        name="market_enum",
        create_type=False,
    )


def upgrade() -> None:
    op.create_table(
        "portfolio_dividends",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "account_id",
            sa.BigInteger,
            sa.ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", _market_enum(), nullable=False),
        sa.Column("dividend_type", sa.String(length=10), nullable=False),
        sa.Column("ex_dividend_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("amount_per_share", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("quantity_at_record", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="TWD",
        ),
        sa.Column(
            "withholding_tax",
            sa.Numeric(precision=24, scale=8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "dividend_type IN ('CASH', 'STOCK')",
            name="ck_portfolio_dividends_type_valid",
        ),
        sa.CheckConstraint(
            "amount_per_share > 0",
            name="ck_portfolio_dividends_amount_positive",
        ),
        sa.CheckConstraint(
            "quantity_at_record > 0",
            name="ck_portfolio_dividends_qty_positive",
        ),
        sa.CheckConstraint(
            "withholding_tax >= 0",
            name="ck_portfolio_dividends_withholding_nonneg",
        ),
    )
    op.create_index(
        "ix_portfolio_dividends_account_ex_date",
        "portfolio_dividends",
        ["account_id", "ex_dividend_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_dividends_account_ex_date",
        table_name="portfolio_dividends",
    )
    op.drop_table("portfolio_dividends")
