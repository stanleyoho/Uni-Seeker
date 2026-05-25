import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.modules.price_estimator.composite import CompositeEstimator
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


async def run_valuation_sync(db: AsyncSession, limit: int = 100) -> dict:
    """Run price estimation models for all active stocks."""
    logger.info("start_valuation_sync", limit=limit)

    # 1. Fetch stocks to estimate
    stmt = select(Stock.id).where(Stock.is_active.is_(True)).limit(limit)
    result = await db.execute(stmt)
    stock_ids = [row[0] for row in result.all()]

    estimator = CompositeEstimator(db)
    success_count = 0
    error_count = 0

    for stock_id in stock_ids:
        try:
            res = await estimator.calculate_and_save(stock_id)
            if res:
                success_count += 1
        except Exception as e:
            logger.error("valuation_failed", stock_id=stock_id, error=str(e))
            error_count += 1

    logger.info("finish_valuation_sync", success=success_count, errors=error_count)
    return {"total_processed": len(stock_ids), "success": success_count, "errors": error_count}


class ValuationSyncTask(SyncTask):
    """Sync task that re-calculates valuation estimates for stocks."""

    dataset_name = "valuation"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        # Note: This task doesn't use the rate_limiter as it works on internal DB data
        result = await run_valuation_sync(db, limit=batch_size)

        return SyncResult(
            dataset=self.dataset_name,
            stocks_processed=result["total_processed"],
            records_synced=result["success"],
            errors=result["errors"],
            stopped_reason="completed",
        )
