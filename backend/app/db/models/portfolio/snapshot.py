"""HoldingsSnapshot ORM — Portfolio Tracker Phase 5 / UNI-PORT-003.

One row per `(user_id, account_id, snapshot_date)` triple, or per
`(user_id, NULL, snapshot_date)` for the user-wide roll-up (a virtual
"all accounts" view). Written by the daily snapshot job
(`app.services.portfolio.snapshot_job.take_daily_snapshot_for_user`) and
consumed by `AnalyticsService` for TWR / Sharpe / max-drawdown.

Spec §6 Table 6 (holdings_snapshots Phase 4+) + §14 Q14.8: the existing
`app/models/journal.py::PortfolioSnapshot` table (`portfolio_snapshots`)
is preserved (decision **A — keep**). To avoid namespace conflicts we
use a **different table** here: `holdings_snapshots`. Class name is
`HoldingsSnapshot` for the same reason — `PortfolioSnapshot` is already
mapped elsewhere.

Uniqueness model
----------------
Per spec: 1 row per user × account × day. For the user-wide row we set
`account_id = NULL`. SQLite/Postgres both treat `NULL` as distinct in a
multi-column unique constraint, which is what we want here — the
user-wide row coexists with per-account rows on the same date because
the (user_id, account_id, snapshot_date) tuple differs (`NULL ≠ NULL`
in standard SQL UNIQUE semantics).

We therefore declare ONE UniqueConstraint on the triple. If a stricter
"one user-wide row per day" guarantee is needed later, we can layer a
partial unique index `WHERE account_id IS NULL` in a follow-up
migration; the daily job's UPSERT already enforces this in practice.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.db.models.portfolio.account import PortfolioAccount


class HoldingsSnapshot(Base):
    __tablename__ = "holdings_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "account_id", "snapshot_date",
            name="uq_holdings_snapshots_user_account_date",
        ),
        # spec §6 Table 6 — invariants enforced at the DB layer so a buggy
        # caller (or future raw SQL) cannot persist nonsense.
        CheckConstraint(
            "total_value >= 0",
            name="ck_holdings_snapshots_total_value_nonneg",
        ),
        CheckConstraint(
            "position_count >= 0",
            name="ck_holdings_snapshots_position_count_nonneg",
        ),
        # Hot-path queries — latest-N per user / per account.
        Index(
            "ix_holdings_snapshots_user_date",
            "user_id", "snapshot_date",
        ),
        Index(
            "ix_holdings_snapshots_account_date",
            "account_id", "snapshot_date",
        ),
    )

    # non-default fields first (MappedAsDataclass)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )
    total_value: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    total_unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False
    )
    realized_pnl_cum: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False
    )
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # defaulted / nullable fields after
    account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
        default=None,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )

    account: Mapped[PortfolioAccount | None] = relationship(
        "PortfolioAccount",
        init=False,
        # No back_populates: PortfolioAccount intentionally does not list
        # snapshots in its rel-set (Phase 5 add-on; keeps the cascade
        # graph minimal — snapshot rows are managed by the job, not by
        # account lifecycle).
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<HoldingsSnapshot id={self.id} user_id={self.user_id} "
            f"account_id={self.account_id} date={self.snapshot_date} "
            f"value={self.total_value} pos={self.position_count}>"
        )
