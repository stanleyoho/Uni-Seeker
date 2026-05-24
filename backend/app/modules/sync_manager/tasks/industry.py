import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.modules.industry.aggregator import IndustryAggregator
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


class IndustryAggregatesSyncTask(SyncTask):
    """Sync task that calculates industry-level aggregate metrics."""

    dataset_name = "industry_aggregates"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        """Run the industry aggregator for the latest available period."""
        logger.info("start_industry_aggregates_sync")

        # 1. Determine the latest period available in the system
        period_query = (
            select(FinancialMetrics.period)
            .order_by(FinancialMetrics.period.desc())
            .limit(1)
        )
        period_result = await db.execute(period_query)
        period = period_result.scalar_one_or_none()

        if not period:
            logger.warning("industry_aggregates_no_period_found")
            return SyncResult(
                dataset=self.dataset_name,
                stocks_processed=0,
                records_synced=0,
                errors=0,
                stopped_reason="completed",
            )

        # 2. Run aggregator
        try:
            aggregator = IndustryAggregator(db)
            await aggregator.aggregate_all_industries(period)

            logger.info("finish_industry_aggregates_sync", period=period)
            return SyncResult(
                dataset=self.dataset_name,
                stocks_processed=0,
                records_synced=1,
                errors=0,
                stopped_reason="completed",
            )
        except Exception as e:
            logger.error("industry_aggregates_sync_failed", error=str(e))
            return SyncResult(
                dataset=self.dataset_name,
                stocks_processed=0,
                records_synced=0,
                errors=1,
                stopped_reason="error",
                error_details=[str(e)],
            )
