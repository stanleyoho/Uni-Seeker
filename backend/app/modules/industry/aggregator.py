import statistics
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.models.industry import Industry
from app.models.industry_metrics import IndustryMetrics
from app.models.stock import Stock
from app.models.valuation import StockValuation


class IndustryAggregator:
    """Calculates and stores aggregate metrics for each industry."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def aggregate_all_industries(self, period: str):
        """Aggregate metrics for all active industries for a given period."""
        result = await self.session.execute(select(Industry))
        industries = result.scalars().all()

        for industry in industries:
            await self.aggregate_industry(industry.id, period)

        await self.session.commit()

    async def aggregate_industry(self, industry_id: int, period: str):
        """Calculate and store median metrics for a single industry."""
        # Get active stocks in this industry
        stock_ids_query = select(Stock.id).where(
            Stock.industry_id == industry_id, Stock.is_active == True
        )
        stock_ids_result = await self.session.execute(stock_ids_query)
        stock_ids = stock_ids_result.scalars().all()

        if not stock_ids:
            return

        # Fetch quarterly metrics for the period
        metrics_query = select(FinancialMetrics).where(
            FinancialMetrics.stock_id.in_(stock_ids), FinancialMetrics.period == period
        )
        metrics = (await self.session.execute(metrics_query)).scalars().all()

        # Fetch latest daily valuations for each stock
        latest_val_subquery = (
            select(
                StockValuation.stock_id, func.max(StockValuation.date).label("max_date")
            )
            .where(StockValuation.stock_id.in_(stock_ids))
            .group_by(StockValuation.stock_id)
            .subquery()
        )

        val_query = select(StockValuation).join(
            latest_val_subquery,
            and_(
                StockValuation.stock_id == latest_val_subquery.c.stock_id,
                StockValuation.date == latest_val_subquery.c.max_date,
            ),
        )
        valuations = (await self.session.execute(val_query)).scalars().all()

        def get_median(values: List[Optional[float]]) -> Optional[float]:
            clean_values = [v for v in values if v is not None]
            if not clean_values:
                return None
            return float(statistics.median(clean_values))

        # Calculate medians
        metrics_data = {
            "median_roe": get_median([m.roe for m in metrics]),
            "median_roa": get_median([m.roa for m in metrics]),
            "median_gross_margin": get_median([m.gross_margin for m in metrics]),
            "median_operating_margin": get_median([m.operating_margin for m in metrics]),
            "median_net_margin": get_median([m.net_margin for m in metrics]),
            "median_revenue_growth_yoy": get_median(
                [m.revenue_growth_yoy for m in metrics]
            ),
        }

        val_data = {
            "median_pe": get_median(
                [
                    float(v.pe_ratio)
                    for v in valuations
                    if v.pe_ratio is not None and v.pe_ratio > 0
                ]
            ),
            "median_pb": get_median(
                [
                    float(v.pb_ratio)
                    for v in valuations
                    if v.pb_ratio is not None and v.pb_ratio > 0
                ]
            ),
            "median_yield": get_median(
                [float(v.dividend_yield) for v in valuations if v.dividend_yield is not None]
            ),
        }

        # Check for existing record
        metric_record_query = select(IndustryMetrics).where(
            IndustryMetrics.industry_id == industry_id, IndustryMetrics.period == period
        )
        metric_record = (
            (await self.session.execute(metric_record_query)).scalars().first()
        )

        if not metric_record:
            metric_record = IndustryMetrics(
                industry_id=industry_id,
                period=period,
                **metrics_data,
                **val_data,
            )
            self.session.add(metric_record)
        else:
            for k, v in {**metrics_data, **val_data}.items():
                setattr(metric_record, k, v)
