"""Sync task: daily stock prices (TaiwanStockPrice)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindClient, FinMindRateLimitError
from app.config import settings
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


class PriceSyncTask(SyncTask):
    """Synchronise daily OHLCV prices for all tracked stocks."""

    dataset_name = "prices"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)
        today = date.today()

        # -- load all active stocks ---------------------------------------
        stocks_q = await db.execute(
            select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.id)
        )
        stocks = stocks_q.scalars().all()

        if not stocks:
            result.stopped_reason = "completed"
            return result

        # -- load existing sync states keyed by stock_id ------------------
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
            # Determine start_date from last sync state
            state = sync_map.get(stock.id)
            if state and state.last_synced_date and state.last_synced_date >= today:
                continue  # already up to date

            start_date = (
                (state.last_synced_date + timedelta(days=1))
                if state and state.last_synced_date
                else date(2020, 1, 1)
            )

            # Strip the .TW suffix for the FinMind data_id
            data_id = stock.symbol.replace(".TW", "")

            # -- acquire rate-limit permit --------------------------------
            if not await rate_limiter.wait_and_acquire(timeout=30):
                result.stopped_reason = "rate_limit"
                logger.warning("price_sync_rate_limit", stock=stock.symbol)
                break

            try:
                raw = await client.fetch(
                    dataset="TaiwanStockPrice",
                    data_id=data_id,
                    start_date=start_date.isoformat(),
                    end_date=today.isoformat(),
                )
            except FinMindRateLimitError:
                result.stopped_reason = "rate_limit"
                logger.warning("price_sync_api_rate_limit", stock=stock.symbol)
                break
            except Exception as exc:
                logger.error(
                    "price_sync_fetch_error",
                    stock=stock.symbol,
                    error=str(exc),
                )
                result.errors += 1
                result.error_details.append(f"{stock.symbol}: {exc}")
                continue

            # -- upsert price rows ----------------------------------------
            max_date = start_date
            for row in raw:
                try:
                    row_date = date.fromisoformat(row["date"])
                    open_val = Decimal(str(row["open"]))
                    high_val = Decimal(str(row["max"]))
                    low_val = Decimal(str(row["min"]))
                    close_val = Decimal(str(row["close"]))
                    volume = int(row["Trading_Volume"])
                    change = Decimal(str(row.get("spread", 0)))
                except (KeyError, ValueError, InvalidOperation) as exc:
                    logger.warning(
                        "price_sync_skip_row",
                        stock=stock.symbol,
                        error=str(exc),
                    )
                    continue

                # Compute change_percent
                prev_close = close_val - change if change else None
                change_pct = (
                    (change / prev_close * 100)
                    if prev_close and prev_close != 0
                    else Decimal("0")
                )

                stmt = pg_insert(StockPrice).values(
                    stock_id=stock.id,
                    date=row_date,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    volume=volume,
                    change=change,
                    change_percent=change_pct,
                )
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_stock_prices_stock_id_date",
                )
                await db.execute(stmt)
                result.records_synced += 1
                if row_date > max_date:
                    max_date = row_date

            # -- update sync state for this stock -------------------------
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

            # Pause every batch_size stocks to avoid overwhelming the DB
            if processed % batch_size == 0:
                logger.info(
                    "price_sync_batch_checkpoint",
                    processed=processed,
                    remaining=rate_limiter.remaining,
                )
                if rate_limiter.remaining < 5:
                    result.stopped_reason = "rate_limit"
                    break

        if result.stopped_reason is None:
            result.stopped_reason = "completed"

        logger.info(
            "price_sync_finished",
            stocks_processed=result.stocks_processed,
            records=result.records_synced,
            stopped=result.stopped_reason,
        )
        return result
