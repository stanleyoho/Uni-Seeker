"""Add hot-path indexes: stock_prices.date, stocks.is_active, stocks.market.

Revision ID: UNI_PERF_001
Revises: UNI_SYNC_002
Create Date: 2026-06-01

Background
==========
The November 2026 audit profiled the three slowest hot-path endpoints
and identified missing single-column indexes that force seq-scans on
otherwise tiny tables:

1. ``stock_prices.date`` — the heatmap pipeline uses
   ``SELECT MAX(date) FROM stock_prices`` to pick the latest trading
   day then re-queries ``WHERE date = latest_date``. Without this
   index the MAX scan was the 2nd-slowest line in pg_stat_statements.

2. ``stocks.is_active`` — scanner / screener filter on this column
   every call. With ~1500 stocks the seq-scan is bearable but the
   index is essentially free (boolean column, BRIN or plain BTREE).

3. ``stocks.market`` — heatmap uses
   ``WHERE market = 'TW_TWSE'`` to scope the sector aggregations.
   Same story as ``is_active``: cheap to add, removes the seq-scan.

The composite ``ix_stock_prices_stock_id_date`` index already exists
(model declaration in ``app.models.price``) and services the
per-stock IN-clause batches added by the N+1 fixes in the same PR.
The new single-column ``date`` index complements that one — they
satisfy different queries.

Naming
======
``ix_<table>_<column>`` matches the prevailing convention in the
codebase (cf. ``ix_stock_prices_stock_id_date``). No collision with
existing index names was found via ``grep -rn 'Index(' app/models``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "UNI_PERF_001"
down_revision: str | None = "UNI_SYNC_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Index name constants — declared at module scope so the upgrade/downgrade
# pair stays in sync and grep can locate them.
IX_STOCK_PRICES_DATE = "ix_stock_prices_date"
IX_STOCKS_IS_ACTIVE = "ix_stocks_is_active"
IX_STOCKS_MARKET = "ix_stocks_market"


def upgrade() -> None:
    # ``stock_prices.date`` — heatmap MAX(date) + filter.
    op.create_index(IX_STOCK_PRICES_DATE, "stock_prices", ["date"])
    # ``stocks.is_active`` — scanner / screener / low-base filters.
    op.create_index(IX_STOCKS_IS_ACTIVE, "stocks", ["is_active"])
    # ``stocks.market`` — heatmap sector scope filter.
    op.create_index(IX_STOCKS_MARKET, "stocks", ["market"])


def downgrade() -> None:
    op.drop_index(IX_STOCKS_MARKET, table_name="stocks")
    op.drop_index(IX_STOCKS_IS_ACTIVE, table_name="stocks")
    op.drop_index(IX_STOCK_PRICES_DATE, table_name="stock_prices")
