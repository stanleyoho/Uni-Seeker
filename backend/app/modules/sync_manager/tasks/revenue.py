"""Sync task: Monthly Revenue (TaiwanStockMonthRevenue)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revenue import MonthlyRevenue
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindClient, FinMindRateLimitError
from app.config import settings
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


def _safe_decimal(value: object) -> Decimal | None:
    """Convert a value to Decimal, returning None for empty / invalid data."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_period(row_date: str) -> str | None:
    """Convert a FinMind date string (e.g. '2026-03-01') to period 'YYYY-MM'."""
    try:
        d = date.fromisoformat(row_date)
        return f"{d.year}-{d.month:02d}"
    except (ValueError, TypeError):
        return None


class RevenueSyncTask(SyncTask):
    """Synchronise monthly revenue for all tracked stocks."""

    dataset_name = "revenue"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)
        today = date.today()

        # -- load active stocks -------------------------------------------
        stocks_q = await db.execute(
            select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.id)
        )
        stocks = stocks_q.scalars().all()

        if not stocks:
            result.stopped_reason = "completed"
            return result

        # -- sync state map -----------------------------------------------
        sync_q = await db.execute(
            select(SyncState).where(SyncState.dataset == self.dataset_name)
        )
        sync_map: dict[int | None, SyncState] = {
            s.stock_id: s for s in sync_q.scalars().all()
        }

        client = FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

        processed = 0
        for stock in stocks:
            state = sync_map.get(stock.id)
            if state and state.last_synced_date and state.last_synced_date >= today:
                continue

            start_date = (
                (state.last_synced_date + timedelta(days=1))
                if state and state.last_synced_date
                else date(2020, 1, 1)
            )
            data_id = stock.symbol.replace(".TW", "")

            if not await rate_limiter.wait_and_acquire(timeout=30):
                result.stopped_reason = "rate_limit"
                break

            try:
                raw = await client.fetch(
                    dataset="TaiwanStockMonthRevenue",
                    data_id=data_id,
                    start_date=start_date.isoformat(),
                    end_date=today.isoformat(),
                )
            except FinMindRateLimitError:
                result.stopped_reason = "rate_limit"
                break
            except Exception as exc:
                logger.error(
                    "revenue_sync_fetch_error",
                    stock=stock.symbol,
                    error=str(exc),
                )
                result.errors += 1
                result.error_details.append(f"{stock.symbol}: {exc}")
                continue

            max_date = start_date
            for row in raw:
                period = _to_period(row.get("date", ""))
                if period is None:
                    continue

                revenue = _safe_decimal(row.get("revenue"))
                if revenue is None:
                    continue

                mom = _safe_decimal(row.get("revenue_month"))
                yoy = _safe_decimal(row.get("revenue_year"))

                try:
                    row_date = date.fromisoformat(row["date"])
                except (KeyError, ValueError):
                    continue

                stmt = pg_insert(MonthlyRevenue).values(
                    stock_id=stock.id,
                    period=period,
                    revenue=revenue,
                    mom_growth=mom,
                    yoy_growth=yoy,
                    currency="TWD",
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_monthly_revenues_stock_id_period",
                    set_={
                        "revenue": stmt.excluded.revenue,
                        "mom_growth": stmt.excluded.mom_growth,
                        "yoy_growth": stmt.excluded.yoy_growth,
                    },
                )
                await db.execute(stmt)
                result.records_synced += 1
                if row_date > max_date:
                    max_date = row_date

            # -- update sync state ----------------------------------------
            now = datetime.now(timezone.utc)
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
                constraint="uq_sync_state_with_stock",
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
            "revenue_sync_finished",
            stocks_processed=result.stocks_processed,
            records=result.records_synced,
            stopped=result.stopped_reason,
        )
        return result
