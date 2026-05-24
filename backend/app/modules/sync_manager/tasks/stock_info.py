"""Sync task: Taiwan stock listing (TaiwanStockInfo)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.industry import Industry
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.market_provider import FinMindMarketProvider
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


class StockInfoSyncTask(SyncTask):
    """Synchronise the stocks table from FinMind TaiwanStockInfo.

    This is a whole-market operation (one API call).  It upserts rows in
    the ``stocks`` table and creates missing industries.
    """

    dataset_name = "stock_info"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)

        # -- acquire one API call permit ----------------------------------
        if not await rate_limiter.wait_and_acquire(timeout=30):
            result.stopped_reason = "rate_limit"
            return result

        try:
            provider = FinMindMarketProvider()
            raw = await provider.fetch_stock_info()
        except Exception as exc:
            logger.error("stock_info_fetch_error", error=str(exc))
            result.stopped_reason = "error"
            result.errors = 1
            result.error_details.append(str(exc))
            return result

        # -- build industry lookup ----------------------------------------
        industry_result = await db.execute(select(Industry))
        industry_map: dict[str, int] = {ind.name: ind.id for ind in industry_result.scalars().all()}

        # -- process records ----------------------------------------------
        for record in raw:
            stock_id_str: str = record.get("stock_id", "")
            stock_name: str = record.get("stock_name", "")
            industry_name: str = record.get("industry_category", "") or ""
            market_raw: str = record.get("type", "")

            if not stock_id_str or not stock_name:
                continue

            # Determine market
            market = Market.TW_TPEX if market_raw == "OTC" else Market.TW_TWSE

            # Ensure industry exists
            industry_id: int | None = None
            if industry_name:
                if industry_name not in industry_map:
                    new_ind = Industry(name=industry_name)
                    db.add(new_ind)
                    await db.flush()
                    industry_map[industry_name] = new_ind.id
                industry_id = industry_map[industry_name]

            # Upsert stock
            symbol = f"{stock_id_str}.TW"
            stmt = pg_insert(Stock).values(
                symbol=symbol,
                name=stock_name,
                market=market,
                industry_id=industry_id,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "industry_id": stmt.excluded.industry_id,
                },
            )
            await db.execute(stmt)
            result.records_synced += 1

        result.stocks_processed = result.records_synced

        # -- update sync state (global row, stock_id IS NULL) ---------------
        now = datetime.now(UTC)
        existing = await db.execute(
            select(SyncState).where(
                SyncState.dataset == self.dataset_name,
                SyncState.stock_id.is_(None),
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.last_synced_date = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
            row.last_run_at = now
            row.status = "completed"
            row.records_synced = result.records_synced
            row.error_message = None
        else:
            db.add(
                SyncState(
                    dataset=self.dataset_name,
                    stock_id=None,
                    last_synced_date=datetime.now(tz=ZoneInfo("Asia/Taipei")).date(),
                    last_run_at=now,
                    status="completed",
                    records_synced=result.records_synced,
                    error_message=None,
                )
            )
        await db.commit()

        result.stopped_reason = "completed"
        logger.info(
            "stock_info_sync_completed",
            records=result.records_synced,
        )
        return result
