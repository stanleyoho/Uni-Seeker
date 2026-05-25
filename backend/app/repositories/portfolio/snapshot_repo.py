"""HoldingsSnapshotRepo — CRUD + UPSERT over `holdings_snapshots`.

Spec §5.3 / §6 Table 6 + Phase 5 plan: storage layer for the daily NAV
snapshots that feed TWR / Sharpe / max-drawdown analytics. Per §11 R3
the repo holds no business logic — math lives in
`app.modules.portfolio.analytics`, orchestration in
`app.services.portfolio.analytics_service` /
`app.services.portfolio.snapshot_job`.

User isolation: every public method takes `user_id` and applies it
directly (no JOIN needed — the table carries `user_id` itself).

UPSERT semantics
----------------
The unique key is `(user_id, account_id, snapshot_date)`. We use the
dialect-native ON CONFLICT clause (Postgres prod / SQLite tests) so a
daily snapshot job re-run on the same day overwrites in place instead
of stacking duplicates. **Postgres treats `NULL` as distinct in a
multi-column unique constraint**, so we cannot rely on plain
ON CONFLICT for the user-wide (account_id IS NULL) row — we
explicitly detect-and-update there. The detect-then-write path is
race-tolerant within the snapshot-job's single-user transaction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.portfolio.snapshot import HoldingsSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class HoldingsSnapshotRepo:
    """CRUD + UPSERT. Single source of truth for `holdings_snapshots`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── writes ──────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        user_id: int,
        account_id: int | None,
        snapshot_date: date,
        total_value: Decimal,
        total_cost: Decimal,
        total_unrealized_pnl: Decimal,
        realized_pnl_cum: Decimal,
        position_count: int,
    ) -> HoldingsSnapshot:
        """Plain INSERT — raises IntegrityError on conflict. Callers should
        prefer `upsert` for the daily-job idempotency contract."""
        row = HoldingsSnapshot(
            user_id=user_id,
            snapshot_date=snapshot_date,
            total_value=total_value,
            total_cost=total_cost,
            total_unrealized_pnl=total_unrealized_pnl,
            realized_pnl_cum=realized_pnl_cum,
            position_count=position_count,
            account_id=account_id,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def upsert(
        self,
        *,
        user_id: int,
        account_id: int | None,
        snapshot_date: date,
        total_value: Decimal,
        total_cost: Decimal,
        total_unrealized_pnl: Decimal,
        realized_pnl_cum: Decimal,
        position_count: int,
    ) -> HoldingsSnapshot:
        """Insert-or-update on `(user_id, account_id, snapshot_date)`.

        Two code paths:
          1. **account_id IS NOT NULL** — straightforward ON CONFLICT
             over the unique constraint (NULL not involved).
          2. **account_id IS NULL** — Postgres treats `NULL` as distinct
             in UNIQUE so ON CONFLICT won't fire; we detect-then-update
             via a normal `SELECT … WHERE account_id IS NULL` round-trip.
             Race window is bounded by the snapshot job's single-user
             transaction (called from a scheduler, not user request).
        """
        if account_id is None:
            existing = await self._get_user_wide(user_id, snapshot_date)
            if existing is not None:
                existing.total_value = total_value
                existing.total_cost = total_cost
                existing.total_unrealized_pnl = total_unrealized_pnl
                existing.realized_pnl_cum = realized_pnl_cum
                existing.position_count = position_count
                await self.db.flush()
                await self.db.refresh(existing)
                return existing
            # Fall through to insert.
            return await self.create(
                user_id=user_id,
                account_id=None,
                snapshot_date=snapshot_date,
                total_value=total_value,
                total_cost=total_cost,
                total_unrealized_pnl=total_unrealized_pnl,
                realized_pnl_cum=realized_pnl_cum,
                position_count=position_count,
            )

        bind = self.db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")

        values = {
            "user_id": user_id,
            "account_id": account_id,
            "snapshot_date": snapshot_date,
            "total_value": total_value,
            "total_cost": total_cost,
            "total_unrealized_pnl": total_unrealized_pnl,
            "realized_pnl_cum": realized_pnl_cum,
            "position_count": position_count,
        }

        if dialect_name == "postgresql":
            stmt = pg_insert(HoldingsSnapshot).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "account_id", "snapshot_date"],
                set_={
                    "total_value": stmt.excluded.total_value,
                    "total_cost": stmt.excluded.total_cost,
                    "total_unrealized_pnl": stmt.excluded.total_unrealized_pnl,
                    "realized_pnl_cum": stmt.excluded.realized_pnl_cum,
                    "position_count": stmt.excluded.position_count,
                },
            )
        else:
            stmt = sqlite_insert(HoldingsSnapshot).values(**values)  # type: ignore[assignment]
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "account_id", "snapshot_date"],
                set_={
                    "total_value": stmt.excluded.total_value,
                    "total_cost": stmt.excluded.total_cost,
                    "total_unrealized_pnl": stmt.excluded.total_unrealized_pnl,
                    "realized_pnl_cum": stmt.excluded.realized_pnl_cum,
                    "position_count": stmt.excluded.position_count,
                },
            )
        await self.db.execute(stmt)
        await self.db.flush()
        return await self._get_per_account(user_id, account_id, snapshot_date)

    # ── reads ───────────────────────────────────────────────────────────

    async def list_by_user(
        self,
        user_id: int,
        date_from: date,
        date_to: date,
        account_id: int | None = None,
    ) -> list[HoldingsSnapshot]:
        """Snapshots for `user_id` between [date_from, date_to] inclusive.

        ``account_id`` filter:
          * a concrete int → that account's rows only
          * ``None``       → the user-wide rows (`account_id IS NULL`)

        Ordered ASC by `snapshot_date` so caller can directly hand the
        list to `analytics.compute_twr` / `daily_returns_from_navs`.
        """
        where = [
            HoldingsSnapshot.user_id == user_id,
            HoldingsSnapshot.snapshot_date >= date_from,
            HoldingsSnapshot.snapshot_date <= date_to,
        ]
        if account_id is None:
            where.append(HoldingsSnapshot.account_id.is_(None))
        else:
            where.append(HoldingsSnapshot.account_id == account_id)

        stmt = (
            select(HoldingsSnapshot)
            .where(and_(*where))
            .order_by(HoldingsSnapshot.snapshot_date.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_user(
        self, user_id: int, account_id: int | None = None
    ) -> HoldingsSnapshot | None:
        """Most-recent snapshot row for the (user, account) scope or
        None if no rows exist. `account_id=None` → user-wide row."""
        where = [HoldingsSnapshot.user_id == user_id]
        if account_id is None:
            where.append(HoldingsSnapshot.account_id.is_(None))
        else:
            where.append(HoldingsSnapshot.account_id == account_id)
        stmt = (
            select(HoldingsSnapshot)
            .where(and_(*where))
            .order_by(HoldingsSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def delete_older_than(self, user_id: int, cutoff: date) -> int:
        """Retention pruning. Returns the number of rows deleted.

        Spec §6 Table 6 hint: free / basic tiers will eventually cap
        history length; the actual cutoff policy lives in the service
        layer (not yet wired up), this method is the pure DB primitive.
        """
        stmt = delete(HoldingsSnapshot).where(
            HoldingsSnapshot.user_id == user_id,
            HoldingsSnapshot.snapshot_date < cutoff,
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ── internals ───────────────────────────────────────────────────────

    async def _get_user_wide(self, user_id: int, snapshot_date: date) -> HoldingsSnapshot | None:
        stmt = select(HoldingsSnapshot).where(
            HoldingsSnapshot.user_id == user_id,
            HoldingsSnapshot.account_id.is_(None),
            HoldingsSnapshot.snapshot_date == snapshot_date,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _get_per_account(
        self, user_id: int, account_id: int, snapshot_date: date
    ) -> HoldingsSnapshot:
        stmt = select(HoldingsSnapshot).where(
            HoldingsSnapshot.user_id == user_id,
            HoldingsSnapshot.account_id == account_id,
            HoldingsSnapshot.snapshot_date == snapshot_date,
        )
        result = await self.db.execute(stmt)
        row = result.scalars().first()
        if row is None:
            # Should never happen after a successful upsert.
            raise RuntimeError(
                "HoldingsSnapshotRepo.upsert: row missing after upsert "
                f"user_id={user_id} account_id={account_id} "
                f"snapshot_date={snapshot_date}"
            )
        return row


__all__ = ["HoldingsSnapshotRepo"]
