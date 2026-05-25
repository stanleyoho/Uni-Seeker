"""Daily snapshot job — captures NAV per account + user-wide.

Phase 5. Spec §6 Table 6 + §11 (holdings_snapshots). Designed to be
called by a scheduler (cron / APScheduler / k8s CronJob — wiring is
**out of scope** for this task; the public functions here are the
contract the scheduler consumes).

Idempotency contract
--------------------
A given (`user_id`, `account_id`, `snapshot_date`) tuple can be
upserted any number of times in a day without creating duplicates —
`HoldingsSnapshotRepo.upsert` rewrites the row atomically. Operators
can safely re-run the job after a partial failure or backfill a
missed day.

Rows written per user
---------------------
For each user with at least one account, the job writes:
  * 1 row per account                (account_id IS NOT NULL)
  * 1 user-wide row                  (account_id IS NULL) ← aggregates
                                       across every account.

If the user has zero positions on a given day, the user-wide row still
gets written with all zeros + position_count=0 so the time series has
no holes (gaps confuse Sharpe / TWR boundary detection).

Live price feed
---------------
The job relies on the same `LivePriceFetcher` Protocol that powers
`/api/v1/holdings/summary`. Caller is responsible for instantiating the
prod / fallback composite (see `app/api/v1/holdings/_deps.py`) — the
job remains protocol-typed for testability.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict


class _PositionTotals(TypedDict):
    """Per-account aggregate snapshot. Strongly typed because the dict
    flows through to `HoldingsSnapshotRepo.upsert` whose columns require
    distinct `Decimal` vs `int` types."""

    total_value: Decimal
    total_cost: Decimal
    total_unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    position_count: int

from sqlalchemy import select

from app.db.models.portfolio.account import PortfolioAccount
from app.repositories.portfolio.account_repo import PortfolioAccountRepo
from app.repositories.portfolio.position_repo import PortfolioPositionRepo
from app.repositories.portfolio.snapshot_repo import HoldingsSnapshotRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.position import PortfolioPosition
    from app.modules.portfolio.live_price_fetcher import LivePriceFetcher


_ZERO = Decimal("0")


async def take_daily_snapshot_for_user(
    db: AsyncSession,
    user_id: int,
    live_price_fetcher: LivePriceFetcher,
    snapshot_date: date | None = None,
) -> int:
    """Capture today's snapshot for one user, returning rows written.

    Steps:
      1. List all accounts for `user_id`.
      2. For each account: load positions, batch-fetch quotes, derive
         (total_value, total_cost, total_unrealized_pnl, realized_pnl_cum,
         position_count). UPSERT one row per account.
      3. Roll the per-account numbers up into 1 user-wide row
         (account_id IS NULL). UPSERT it.

    The function commits its own writes via `db.flush()` calls inside
    the repo — the outer transaction (scheduler-owned) is responsible
    for the final `commit()`.

    Args:
        db: AsyncSession (scheduler-owned transaction).
        user_id: User to snapshot.
        live_price_fetcher: Protocol-typed quote source.
        snapshot_date: Override the snapshot date — defaults to today.
            Exposed for backfill / testing.

    Returns:
        Number of rows written (per-account rows + 1 user-wide row).
        For a user with no accounts the user-wide row is still written
        with all zeros, so the floor is 1.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    account_repo = PortfolioAccountRepo(db)
    position_repo = PortfolioPositionRepo(db)
    snapshot_repo = HoldingsSnapshotRepo(db)

    accounts = await account_repo.list_by_user(user_id)

    # Per-account roll-ups.
    user_total_value = _ZERO
    user_total_cost = _ZERO
    user_total_unrealized = _ZERO
    user_realized_cum = _ZERO
    user_position_count = 0

    rows_written = 0

    for acc in accounts:
        positions = await position_repo.list_by_account(acc.id)
        totals = await _aggregate_positions(positions, live_price_fetcher)

        await snapshot_repo.upsert(
            user_id=user_id,
            account_id=acc.id,
            snapshot_date=snapshot_date,
            total_value=totals["total_value"],
            total_cost=totals["total_cost"],
            total_unrealized_pnl=totals["total_unrealized_pnl"],
            realized_pnl_cum=totals["realized_pnl_cum"],
            position_count=totals["position_count"],
        )
        rows_written += 1

        user_total_value += totals["total_value"]
        user_total_cost += totals["total_cost"]
        user_total_unrealized += totals["total_unrealized_pnl"]
        user_realized_cum += totals["realized_pnl_cum"]
        user_position_count += totals["position_count"]

    # User-wide row — always written, even on an empty portfolio.
    await snapshot_repo.upsert(
        user_id=user_id,
        account_id=None,
        snapshot_date=snapshot_date,
        total_value=user_total_value,
        total_cost=user_total_cost,
        total_unrealized_pnl=user_total_unrealized,
        realized_pnl_cum=user_realized_cum,
        position_count=user_position_count,
    )
    rows_written += 1

    return rows_written


async def take_daily_snapshot_for_all_active_users(
    db: AsyncSession,
    live_price_fetcher: LivePriceFetcher,
    snapshot_date: date | None = None,
) -> dict[int, int]:
    """Capture snapshots for every user owning at least one account.

    The "active user" definition is intentionally narrow — we do not
    snapshot users without any portfolio data, since their user-wide
    row would always be all-zeros and consumes no analytics. Operators
    backfilling history for inactive users can call
    `take_daily_snapshot_for_user` directly.

    Returns:
        Mapping {user_id: rows_written}. Empty when no active users.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    # Distinct user_ids that own at least one account.
    stmt = select(PortfolioAccount.user_id).distinct()
    result = await db.execute(stmt)
    user_ids = [int(uid) for uid in result.scalars().all() if uid is not None]

    out: dict[int, int] = {}
    for uid in user_ids:
        out[uid] = await take_daily_snapshot_for_user(
            db,
            user_id=uid,
            live_price_fetcher=live_price_fetcher,
            snapshot_date=snapshot_date,
        )
    return out


# ── helpers ─────────────────────────────────────────────────────────────


async def _aggregate_positions(
    positions: list[PortfolioPosition],
    fetcher: LivePriceFetcher,
) -> _PositionTotals:
    """Sum positions into per-account totals + count open positions.

    `position_count` is the number of *open* positions (qty > 0),
    matching the `/holdings/summary` semantics. Closed positions still
    contribute to `realized_pnl_cum` (the running realized P&L lives on
    the position row itself).
    """
    total_value = _ZERO
    total_cost = _ZERO
    total_unrealized = _ZERO
    realized_cum = _ZERO
    position_count = 0

    if not positions:
        return {
            "total_value": _ZERO,
            "total_cost": _ZERO,
            "total_unrealized_pnl": _ZERO,
            "realized_pnl_cum": _ZERO,
            "position_count": 0,
        }

    open_positions = [p for p in positions if (p.quantity or _ZERO) > _ZERO]
    # Realized PnL accumulates across both open and closed positions.
    for p in positions:
        realized_cum += p.realized_pnl or _ZERO

    if not open_positions:
        return {
            "total_value": _ZERO,
            "total_cost": _ZERO,
            "total_unrealized_pnl": _ZERO,
            "realized_pnl_cum": realized_cum,
            "position_count": 0,
        }

    symbols = sorted({p.symbol for p in open_positions})
    quotes = await fetcher.fetch_quotes(symbols)

    for p in open_positions:
        qty = p.quantity or _ZERO
        avg = p.avg_cost_fifo or _ZERO
        quote = quotes.get(p.symbol)
        last_price = quote.last_price if quote is not None else avg
        cost = avg * qty
        value = last_price * qty
        total_cost += cost
        total_value += value
        total_unrealized += value - cost
        position_count += 1

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_unrealized_pnl": total_unrealized,
        "realized_pnl_cum": realized_cum,
        "position_count": position_count,
    }


__all__ = [
    "take_daily_snapshot_for_all_active_users",
    "take_daily_snapshot_for_user",
]
