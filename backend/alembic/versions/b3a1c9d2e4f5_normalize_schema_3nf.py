"""normalize schema to 3NF with FK constraints and PG enums

Revision ID: b3a1c9d2e4f5
Revises: 0ef449ae0f1a
Create Date: 2026-04-25 12:00:00.000000

This migration:
- Creates PG enum types (market_enum, user_tier_enum, notification_status_enum)
- Creates industries table and normalizes industry from stocks/valuations/revenues
- Replaces symbol VARCHAR columns with stock_id FK in prices/valuations/margin/revenues
- Adds user_id FK to notification_rules and notification_logs
- Adds status column to notification_logs
- Adds updated_at to tables missing it
- Adds UNIQUE constraint on users.username
- Adds UNIQUE constraint on monthly_revenues(stock_id, period)
- Converts data types: revenue FLOAT->NUMERIC, tier->enum, market->enum
- Creates composite indexes for performance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b3a1c9d2e4f5"
down_revision: Union[str, None] = "0ef449ae0f1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- Enum definitions ----------
market_enum = postgresql.ENUM(
    "TW_TWSE", "TW_TPEX", "US_NYSE", "US_NASDAQ",
    name="market_enum",
    create_type=False,
)

user_tier_enum = postgresql.ENUM(
    "free", "basic", "pro",
    name="user_tier_enum",
    create_type=False,
)

notification_status_enum = postgresql.ENUM(
    "pending", "success", "failed",
    name="notification_status_enum",
    create_type=False,
)


def upgrade() -> None:
    # ============================================================
    # Phase 1: Create PG enum types
    # ============================================================
    op.execute("CREATE TYPE market_enum AS ENUM ('TW_TWSE', 'TW_TPEX', 'US_NYSE', 'US_NASDAQ')")
    op.execute("CREATE TYPE user_tier_enum AS ENUM ('free', 'basic', 'pro')")
    op.execute("CREATE TYPE notification_status_enum AS ENUM ('pending', 'success', 'failed')")

    # ============================================================
    # Phase 2: Create industries table
    # ============================================================
    op.create_table(
        "industries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_industries_name", "industries", ["name"])

    # Populate industries from existing data
    op.execute("""
        INSERT INTO industries (name)
        SELECT DISTINCT industry FROM stocks
        WHERE industry IS NOT NULL AND industry != ''
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO industries (name)
        SELECT DISTINCT industry FROM stock_valuations
        WHERE industry IS NOT NULL AND industry != ''
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO industries (name)
        SELECT DISTINCT industry FROM monthly_revenues
        WHERE industry IS NOT NULL AND industry != ''
        ON CONFLICT (name) DO NOTHING
    """)

    # ============================================================
    # Phase 3: Users table changes
    # ============================================================
    # Add unique constraint on username
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # Add updated_at column
    op.add_column("users", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))

    # Convert tier from varchar to PG enum
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN tier TYPE user_tier_enum
        USING tier::user_tier_enum
    """)

    # ============================================================
    # Phase 4: Stocks table - normalize industry to industry_id
    # ============================================================
    # Convert market from varchar to PG enum
    op.execute("""
        ALTER TABLE stocks
        ALTER COLUMN market TYPE market_enum
        USING market::market_enum
    """)

    # Add industry_id FK column
    op.add_column("stocks", sa.Column(
        "industry_id", sa.Integer(),
        sa.ForeignKey("industries.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.create_index("ix_stocks_industry_id", "stocks", ["industry_id"])

    # Populate industry_id from existing industry text
    op.execute("""
        UPDATE stocks s
        SET industry_id = i.id
        FROM industries i
        WHERE s.industry = i.name
        AND s.industry IS NOT NULL AND s.industry != ''
    """)

    # Drop old industry column
    op.drop_column("stocks", "industry")

    # ============================================================
    # Phase 5: Stock prices - replace symbol with stock_id FK
    # ============================================================
    # Drop old constraints and indexes
    op.drop_constraint("uq_symbol_date", "stock_prices", type_="unique")
    op.drop_index("ix_stock_prices_symbol", table_name="stock_prices")
    op.drop_index("ix_stock_prices_date", table_name="stock_prices")

    # Add stock_id column
    op.add_column("stock_prices", sa.Column("stock_id", sa.Integer(), nullable=True))

    # Populate stock_id from symbol lookup
    op.execute("""
        UPDATE stock_prices sp
        SET stock_id = s.id
        FROM stocks s
        WHERE sp.symbol = s.symbol
    """)

    # Delete orphan rows that have no matching stock
    op.execute("DELETE FROM stock_prices WHERE stock_id IS NULL")

    # Make stock_id NOT NULL and add FK
    op.alter_column("stock_prices", "stock_id", nullable=False)
    op.create_foreign_key(
        "fk_stock_prices_stock_id", "stock_prices",
        "stocks", ["stock_id"], ["id"], ondelete="CASCADE",
    )

    # Drop old symbol and market columns
    op.drop_column("stock_prices", "symbol")
    op.drop_column("stock_prices", "market")

    # Create new indexes and constraint
    op.create_unique_constraint(
        "uq_stock_prices_stock_id_date", "stock_prices", ["stock_id", "date"]
    )
    op.create_index(
        "ix_stock_prices_stock_id_date", "stock_prices", ["stock_id", "date"]
    )

    # ============================================================
    # Phase 6: Stock valuations - replace symbol with stock_id FK
    # ============================================================
    op.drop_constraint("uq_valuation_symbol_date", "stock_valuations", type_="unique")
    op.drop_index("ix_stock_valuations_symbol", table_name="stock_valuations")
    op.drop_index("ix_stock_valuations_date", table_name="stock_valuations")

    op.add_column("stock_valuations", sa.Column("stock_id", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE stock_valuations sv
        SET stock_id = s.id
        FROM stocks s
        WHERE sv.symbol = s.symbol
    """)
    op.execute("DELETE FROM stock_valuations WHERE stock_id IS NULL")

    op.alter_column("stock_valuations", "stock_id", nullable=False)
    op.create_foreign_key(
        "fk_stock_valuations_stock_id", "stock_valuations",
        "stocks", ["stock_id"], ["id"], ondelete="CASCADE",
    )

    # Drop old columns
    op.drop_column("stock_valuations", "symbol")
    op.drop_column("stock_valuations", "industry")

    # Add updated_at
    op.add_column("stock_valuations", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))

    # New indexes
    op.create_unique_constraint(
        "uq_stock_valuations_stock_id_date", "stock_valuations", ["stock_id", "date"]
    )
    op.create_index(
        "ix_stock_valuations_stock_id_date", "stock_valuations", ["stock_id", "date"]
    )

    # ============================================================
    # Phase 7: Margin trading - replace symbol with stock_id FK
    # ============================================================
    op.drop_constraint("uq_margin_symbol_date", "margin_trading", type_="unique")
    op.drop_index("ix_margin_trading_symbol", table_name="margin_trading")
    op.drop_index("ix_margin_trading_date", table_name="margin_trading")

    op.add_column("margin_trading", sa.Column("stock_id", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE margin_trading mt
        SET stock_id = s.id
        FROM stocks s
        WHERE mt.symbol = s.symbol
    """)
    op.execute("DELETE FROM margin_trading WHERE stock_id IS NULL")

    op.alter_column("margin_trading", "stock_id", nullable=False)
    op.create_foreign_key(
        "fk_margin_trading_stock_id", "margin_trading",
        "stocks", ["stock_id"], ["id"], ondelete="CASCADE",
    )

    op.drop_column("margin_trading", "symbol")

    # Add updated_at
    op.add_column("margin_trading", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))

    # New indexes
    op.create_unique_constraint(
        "uq_margin_trading_stock_id_date", "margin_trading", ["stock_id", "date"]
    )
    op.create_index(
        "ix_margin_trading_stock_id_date", "margin_trading", ["stock_id", "date"]
    )

    # ============================================================
    # Phase 8: Monthly revenues - replace symbol with stock_id FK,
    #          fix data types, add UNIQUE
    # ============================================================
    op.drop_index("ix_monthly_revenues_symbol", table_name="monthly_revenues")
    op.drop_index("ix_monthly_revenues_period", table_name="monthly_revenues")

    # Add stock_id column
    op.add_column("monthly_revenues", sa.Column("stock_id", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE monthly_revenues mr
        SET stock_id = s.id
        FROM stocks s
        WHERE mr.symbol = s.symbol
    """)
    op.execute("DELETE FROM monthly_revenues WHERE stock_id IS NULL")

    op.alter_column("monthly_revenues", "stock_id", nullable=False)
    op.create_foreign_key(
        "fk_monthly_revenues_stock_id", "monthly_revenues",
        "stocks", ["stock_id"], ["id"], ondelete="CASCADE",
    )

    # Drop old columns
    op.drop_column("monthly_revenues", "symbol")
    op.drop_column("monthly_revenues", "industry")

    # Convert revenue from FLOAT to NUMERIC(18,2)
    op.alter_column(
        "monthly_revenues", "revenue",
        type_=sa.Numeric(18, 2),
        existing_type=sa.Float(),
        postgresql_using="revenue::numeric(18,2)",
    )

    # Convert growth columns from FLOAT to NUMERIC(10,4)
    op.alter_column(
        "monthly_revenues", "mom_growth",
        type_=sa.Numeric(10, 4),
        existing_type=sa.Float(),
        existing_nullable=True,
        postgresql_using="mom_growth::numeric(10,4)",
    )
    op.alter_column(
        "monthly_revenues", "yoy_growth",
        type_=sa.Numeric(10, 4),
        existing_type=sa.Float(),
        existing_nullable=True,
        postgresql_using="yoy_growth::numeric(10,4)",
    )

    # Add updated_at
    op.add_column("monthly_revenues", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))

    # New UNIQUE and index
    op.create_unique_constraint(
        "uq_monthly_revenues_stock_id_period", "monthly_revenues", ["stock_id", "period"]
    )
    op.create_index(
        "ix_monthly_revenues_stock_id_period", "monthly_revenues", ["stock_id", "period"]
    )

    # ============================================================
    # Phase 9: Notification rules - add user_id FK and updated_at
    # ============================================================
    op.add_column("notification_rules", sa.Column("user_id", sa.Integer(), nullable=True))

    # Set a default user_id for existing rules (first admin or first user)
    op.execute("""
        UPDATE notification_rules
        SET user_id = (SELECT id FROM users ORDER BY is_admin DESC, id ASC LIMIT 1)
        WHERE user_id IS NULL
    """)

    # If no users exist, we still need to handle this -- delete orphans
    op.execute("DELETE FROM notification_rules WHERE user_id IS NULL")

    op.alter_column("notification_rules", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_notification_rules_user_id", "notification_rules",
        "users", ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_notification_rules_user_id", "notification_rules", ["user_id"])

    # Add updated_at
    op.add_column("notification_rules", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))

    # ============================================================
    # Phase 10: Notification logs - add user_id FK, status, updated_at
    # ============================================================
    op.add_column("notification_logs", sa.Column("user_id", sa.Integer(), nullable=True))

    # Populate user_id from the related rule's user_id
    op.execute("""
        UPDATE notification_logs nl
        SET user_id = nr.user_id
        FROM notification_rules nr
        WHERE nl.rule_id = nr.id
    """)

    # For logs without a rule, assign to first user
    op.execute("""
        UPDATE notification_logs
        SET user_id = (SELECT id FROM users ORDER BY is_admin DESC, id ASC LIMIT 1)
        WHERE user_id IS NULL
    """)

    op.execute("DELETE FROM notification_logs WHERE user_id IS NULL")

    op.alter_column("notification_logs", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_notification_logs_user_id", "notification_logs",
        "users", ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_notification_logs_user_id", "notification_logs", ["user_id"])

    # Add FK on rule_id (was missing)
    op.create_foreign_key(
        "fk_notification_logs_rule_id", "notification_logs",
        "notification_rules", ["rule_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_notification_logs_rule_id", "notification_logs", ["rule_id"])

    # Add status column
    op.add_column("notification_logs", sa.Column(
        "status", notification_status_enum,
        server_default="pending", nullable=False,
    ))
    op.create_index("ix_notification_logs_status", "notification_logs", ["status"])

    # Add updated_at
    op.add_column("notification_logs", sa.Column(
        "updated_at", sa.DateTime(timezone=True),
        server_default=sa.text("now()"), nullable=False,
    ))


def downgrade() -> None:
    # ============================================================
    # Reverse Phase 10: notification_logs
    # ============================================================
    op.drop_column("notification_logs", "updated_at")
    op.drop_index("ix_notification_logs_status", table_name="notification_logs")
    op.drop_column("notification_logs", "status")
    op.drop_index("ix_notification_logs_rule_id", table_name="notification_logs")
    op.drop_constraint("fk_notification_logs_rule_id", "notification_logs", type_="foreignkey")
    op.drop_index("ix_notification_logs_user_id", table_name="notification_logs")
    op.drop_constraint("fk_notification_logs_user_id", "notification_logs", type_="foreignkey")
    op.drop_column("notification_logs", "user_id")

    # ============================================================
    # Reverse Phase 9: notification_rules
    # ============================================================
    op.drop_column("notification_rules", "updated_at")
    op.drop_index("ix_notification_rules_user_id", table_name="notification_rules")
    op.drop_constraint("fk_notification_rules_user_id", "notification_rules", type_="foreignkey")
    op.drop_column("notification_rules", "user_id")

    # ============================================================
    # Reverse Phase 8: monthly_revenues
    # ============================================================
    op.drop_index("ix_monthly_revenues_stock_id_period", table_name="monthly_revenues")
    op.drop_constraint("uq_monthly_revenues_stock_id_period", "monthly_revenues", type_="unique")
    op.drop_column("monthly_revenues", "updated_at")

    op.alter_column("monthly_revenues", "yoy_growth", type_=sa.Float(), existing_nullable=True)
    op.alter_column("monthly_revenues", "mom_growth", type_=sa.Float(), existing_nullable=True)
    op.alter_column("monthly_revenues", "revenue", type_=sa.Float())

    # Re-add industry and symbol columns
    op.add_column("monthly_revenues", sa.Column("industry", sa.String(50), server_default="", nullable=False))
    op.add_column("monthly_revenues", sa.Column("symbol", sa.String(20), nullable=True))

    op.execute("""
        UPDATE monthly_revenues mr
        SET symbol = s.symbol
        FROM stocks s
        WHERE mr.stock_id = s.id
    """)
    op.alter_column("monthly_revenues", "symbol", nullable=False)

    op.drop_constraint("fk_monthly_revenues_stock_id", "monthly_revenues", type_="foreignkey")
    op.drop_column("monthly_revenues", "stock_id")

    op.create_index("ix_monthly_revenues_period", "monthly_revenues", ["period"])
    op.create_index("ix_monthly_revenues_symbol", "monthly_revenues", ["symbol"])

    # ============================================================
    # Reverse Phase 7: margin_trading
    # ============================================================
    op.drop_index("ix_margin_trading_stock_id_date", table_name="margin_trading")
    op.drop_constraint("uq_margin_trading_stock_id_date", "margin_trading", type_="unique")
    op.drop_column("margin_trading", "updated_at")

    op.add_column("margin_trading", sa.Column("symbol", sa.String(20), nullable=True))
    op.execute("""
        UPDATE margin_trading mt
        SET symbol = s.symbol
        FROM stocks s
        WHERE mt.stock_id = s.id
    """)
    op.alter_column("margin_trading", "symbol", nullable=False)

    op.drop_constraint("fk_margin_trading_stock_id", "margin_trading", type_="foreignkey")
    op.drop_column("margin_trading", "stock_id")

    op.create_index("ix_margin_trading_date", "margin_trading", ["date"])
    op.create_index("ix_margin_trading_symbol", "margin_trading", ["symbol"])
    op.create_unique_constraint("uq_margin_symbol_date", "margin_trading", ["symbol", "date"])

    # ============================================================
    # Reverse Phase 6: stock_valuations
    # ============================================================
    op.drop_index("ix_stock_valuations_stock_id_date", table_name="stock_valuations")
    op.drop_constraint("uq_stock_valuations_stock_id_date", "stock_valuations", type_="unique")
    op.drop_column("stock_valuations", "updated_at")

    op.add_column("stock_valuations", sa.Column("industry", sa.String(100), server_default="", nullable=False))
    op.add_column("stock_valuations", sa.Column("symbol", sa.String(20), nullable=True))
    op.execute("""
        UPDATE stock_valuations sv
        SET symbol = s.symbol
        FROM stocks s
        WHERE sv.stock_id = s.id
    """)
    op.alter_column("stock_valuations", "symbol", nullable=False)

    op.drop_constraint("fk_stock_valuations_stock_id", "stock_valuations", type_="foreignkey")
    op.drop_column("stock_valuations", "stock_id")

    op.create_index("ix_stock_valuations_date", "stock_valuations", ["date"])
    op.create_index("ix_stock_valuations_symbol", "stock_valuations", ["symbol"])
    op.create_unique_constraint("uq_valuation_symbol_date", "stock_valuations", ["symbol", "date"])

    # ============================================================
    # Reverse Phase 5: stock_prices
    # ============================================================
    op.drop_index("ix_stock_prices_stock_id_date", table_name="stock_prices")
    op.drop_constraint("uq_stock_prices_stock_id_date", "stock_prices", type_="unique")

    op.add_column("stock_prices", sa.Column(
        "market", sa.String(20), nullable=True,
    ))
    op.add_column("stock_prices", sa.Column("symbol", sa.String(20), nullable=True))
    op.execute("""
        UPDATE stock_prices sp
        SET symbol = s.symbol, market = s.market::text
        FROM stocks s
        WHERE sp.stock_id = s.id
    """)
    op.alter_column("stock_prices", "symbol", nullable=False)

    op.drop_constraint("fk_stock_prices_stock_id", "stock_prices", type_="foreignkey")
    op.drop_column("stock_prices", "stock_id")

    op.create_index("ix_stock_prices_date", "stock_prices", ["date"])
    op.create_index("ix_stock_prices_symbol", "stock_prices", ["symbol"])
    op.create_unique_constraint("uq_symbol_date", "stock_prices", ["symbol", "date"])

    # ============================================================
    # Reverse Phase 4: stocks
    # ============================================================
    op.add_column("stocks", sa.Column("industry", sa.String(100), server_default="", nullable=False))
    op.execute("""
        UPDATE stocks s
        SET industry = COALESCE(i.name, '')
        FROM industries i
        WHERE s.industry_id = i.id
    """)

    op.drop_index("ix_stocks_industry_id", table_name="stocks")
    op.drop_column("stocks", "industry_id")

    # Revert market enum to varchar
    op.execute("""
        ALTER TABLE stocks
        ALTER COLUMN market TYPE varchar(20)
        USING market::text
    """)

    # ============================================================
    # Reverse Phase 3: users
    # ============================================================
    op.drop_column("users", "updated_at")

    # Revert tier enum to varchar
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN tier TYPE varchar(20)
        USING tier::text
    """)

    op.drop_constraint("uq_users_username", "users", type_="unique")

    # ============================================================
    # Reverse Phase 2: industries
    # ============================================================
    op.drop_index("ix_industries_name", table_name="industries")
    op.drop_table("industries")

    # ============================================================
    # Reverse Phase 1: Drop PG enum types
    # ============================================================
    op.execute("DROP TYPE IF EXISTS notification_status_enum")
    op.execute("DROP TYPE IF EXISTS user_tier_enum")
    op.execute("DROP TYPE IF EXISTS market_enum")
