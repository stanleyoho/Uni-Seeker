"""Sync task: TW 三大法人 (TaiwanStockInstitutionalInvestorsBuySell).

Each FinMind row carries one investor *category* per (stock, date), e.g.

    {"date": "2026-05-29", "stock_id": "2330", "name": "Foreign_Investor",
     "buy": 12345678, "sell": 8765432}

We aggregate three categories into one row per (stock_id, date):

    Foreign_Investor                      → foreign_net
    Investment_Trust                      → trust_net
    Dealer_self  + Dealer_Hedging         → dealer_net

The aggregation mirrors ``app/api/v1/institutional/legacy.py`` so the
sync semantics match the existing live FinMind passthrough.

Failure model:
  - FinMind rate-limit → stop the batch cleanly, surface in SyncResult.
  - Per-stock fetch error → log + bump errors, continue with next stock
    (one bad ticker must not break the whole sync — same posture as
    margin.py).
  - Per-row parse error → log + skip, continue with next row.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.models.tw_institutional import TwInstitutionalNet
from app.modules.finmind.client import FinMindClient, FinMindRateLimitError
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()

# Maps FinMind ``name`` column to our 3-bucket schema. Dealer rolls up
# the two sub-categories (self + hedging) because day-traders read
# them as a single signal in practice.
_CATEGORY_MAP: dict[str, str] = {
    "Foreign_Investor": "foreign",
    "Investment_Trust": "trust",
    "Dealer_self": "dealer",
    "Dealer_Hedging": "dealer",
}


def _aggregate_rows(
    raw: list[dict[str, Any]],
) -> dict[date, dict[str, int]]:
    """Aggregate raw FinMind records by date → {foreign,trust,dealer}_net."""
    buckets: dict[date, dict[str, int]] = defaultdict(
        lambda: {"foreign_net": 0, "trust_net": 0, "dealer_net": 0}
    )
    for row in raw:
        cat = _CATEGORY_MAP.get(row.get("name", ""))
        if cat is None:
            continue
        try:
            row_date = date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        buy = int(row.get("buy", 0) or 0)
        sell = int(row.get("sell", 0) or 0)
        buckets[row_date][f"{cat}_net"] += buy - sell
    return buckets


class TwInstitutionalSyncTask(SyncTask):
    """Synchronise TW 三大法人 daily net flow for all tracked stocks."""

    dataset_name = "tw_institutional"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)
        today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()

        stocks_q = await db.execute(
            select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.id)
        )
        stocks = stocks_q.scalars().all()

        if not stocks:
            result.stopped_reason = "completed"
            return result

        sync_q = await db.execute(select(SyncState).where(SyncState.dataset == self.dataset_name))
        sync_map: dict[int | None, SyncState] = {s.stock_id: s for s in sync_q.scalars().all()}

        client = FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

        processed = 0
        for stock in stocks:
            state = sync_map.get(stock.id)
            if state and state.last_synced_date and state.last_synced_date >= today:
                continue

            # First run starts ~30 days back (not all the way to 2020 like
            # price data) — institutional flow is most useful as a recent
            # signal. Steady state: pull from day after last sync to today.
            start_date = (
                (state.last_synced_date + timedelta(days=1))
                if state and state.last_synced_date
                else today - timedelta(days=30)
            )

            if start_date > today:
                continue

            data_id = stock.symbol.replace(".TW", "").replace(".TWO", "")

            if not await rate_limiter.wait_and_acquire(timeout=30):
                result.stopped_reason = "rate_limit"
                break

            try:
                raw = await client.fetch(
                    dataset="TaiwanStockInstitutionalInvestorsBuySell",
                    data_id=data_id,
                    start_date=start_date.isoformat(),
                    end_date=today.isoformat(),
                )
            except FinMindRateLimitError:
                result.stopped_reason = "rate_limit"
                break
            except Exception as exc:
                # Defensive: one bad ticker (4xx, JSON parse, etc.) must
                # not abort the entire scheduler chain.
                logger.warning(
                    "tw_institutional_sync_fetch_error",
                    stock=stock.symbol,
                    error=str(exc),
                )
                result.errors += 1
                result.error_details.append(f"{stock.symbol}: {exc}")
                continue

            buckets = _aggregate_rows(raw)
            max_date = start_date

            for row_date, nets in sorted(buckets.items()):
                foreign = nets["foreign_net"]
                trust = nets["trust_net"]
                dealer = nets["dealer_net"]
                total = foreign + trust + dealer

                stmt = pg_insert(TwInstitutionalNet).values(
                    stock_id=stock.id,
                    date=row_date,
                    foreign_net=foreign,
                    trust_net=trust,
                    dealer_net=dealer,
                    total_net=total,
                )
                # UPSERT — re-running the day's sync re-overwrites the
                # row (FinMind sometimes restates today's numbers later).
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_tw_institutional_net_stock_date",
                    set_={
                        "foreign_net": foreign,
                        "trust_net": trust,
                        "dealer_net": dealer,
                        "total_net": total,
                    },
                )
                await db.execute(stmt)
                result.records_synced += 1
                if row_date > max_date:
                    max_date = row_date

            # Per-stock sync state UPSERT. Matches the margin.py pattern.
            now = datetime.now(UTC)
            sync_stmt = pg_insert(SyncState).values(
                dataset=self.dataset_name,
                stock_id=stock.id,
                last_synced_date=max_date,
                last_run_at=now,
                status="completed",
                records_synced=result.records_synced,
                error_message=None,
            )
            sync_stmt = sync_stmt.on_conflict_do_update(
                index_elements=["dataset", "stock_id"],
                index_where=text("stock_id IS NOT NULL"),
                set_={
                    "last_synced_date": max_date,
                    "last_run_at": now,
                    "status": "completed",
                    "records_synced": sync_stmt.excluded.records_synced,
                    "error_message": None,
                },
            )
            await db.execute(sync_stmt)
            await db.commit()

            processed += 1
            result.stocks_processed = processed

            if processed % batch_size == 0 and rate_limiter.remaining < 5:
                result.stopped_reason = "rate_limit"
                break

        if result.stopped_reason is None:
            result.stopped_reason = "completed"

        logger.info(
            "tw_institutional_sync_finished",
            stocks_processed=result.stocks_processed,
            records=result.records_synced,
            stopped=result.stopped_reason,
        )
        return result
