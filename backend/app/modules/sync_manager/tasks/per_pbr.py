"""Sync task: PER / PBR / dividend yield (TaiwanStockPER)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.models.valuation import StockValuation
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


class PerPbrSyncTask(SyncTask):
    """Synchronise PER, PBR and dividend yield for all tracked stocks."""

    dataset_name = "per_pbr"

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
                    dataset="TaiwanStockPER",
                    data_id=data_id,
                    start_date=start_date.isoformat(),
                    end_date=today.isoformat(),
                )
            except FinMindRateLimitError:
                result.stopped_reason = "rate_limit"
                break
            except Exception as exc:
                logger.error(
                    "per_pbr_sync_fetch_error",
                    stock=stock.symbol,
                    error=str(exc),
                )
                result.errors += 1
                result.error_details.append(f"{stock.symbol}: {exc}")
                continue

            max_date = start_date
            for row in raw:
                try:
                    row_date = date.fromisoformat(row["date"])
                except (KeyError, ValueError):
                    continue

                pe = _safe_decimal(row.get("PER"))
                pb = _safe_decimal(row.get("PBR"))
                dy = _safe_decimal(row.get("dividend_yield"))

                stmt = pg_insert(StockValuation).values(
                    stock_id=stock.id,
                    date=row_date,
                    pe_ratio=pe,
                    pb_ratio=pb,
                    dividend_yield=dy,
                )
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_stock_valuations_stock_id_date",
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
                constraint="uq_sync_state",
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
            "per_pbr_sync_finished",
            stocks_processed=result.stocks_processed,
            records=result.records_synced,
            stopped=result.stopped_reason,
        )
        return result
