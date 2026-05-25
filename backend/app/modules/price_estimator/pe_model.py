from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.models.valuation import StockValuation
from app.modules.price_estimator.base import EstimateResult
from app.modules.price_estimator.utils import ValuationUtils


class PEBandEstimator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def estimate(self, stock_id: int) -> EstimateResult:
        # 1. Fetch historical PE ratios
        pe_query = (
            select(StockValuation.pe_ratio)
            .where(StockValuation.stock_id == stock_id)
            .where(StockValuation.pe_ratio.is_not(None))
            .where(StockValuation.pe_ratio > 0)
            .order_by(StockValuation.date.desc())
            .limit(750)
        )
        result = await self.session.execute(pe_query)
        raw_pe = [float(row[0]) for row in result.all()]

        # 2. Clean outliers
        pe_list = ValuationUtils.clean_outliers(raw_pe)

        # 3. Fetch latest TTM EPS
        eps_query = (
            select(FinancialMetrics.eps)
            .where(FinancialMetrics.stock_id == stock_id)
            .where(FinancialMetrics.eps.is_not(None))
            .order_by(FinancialMetrics.period.desc())
            .limit(4)
        )
        eps_result = await self.session.execute(eps_query)
        ttm_eps = sum([float(row[0]) for row in eps_result.all()])

        if len(pe_list) < 20 or ttm_eps <= 0:
            return EstimateResult(
                model_type="pe_band",
                cheap_price=None,
                fair_price=None,
                expensive_price=None,
                confidence=Decimal("0.0"),
                details={"reason": "Insufficient PE data or negative EPS"},
            )

        # 4. Calculate stats
        pe_25 = np.percentile(pe_list, 25)
        pe_50 = np.percentile(pe_list, 50)
        pe_75 = np.percentile(pe_list, 75)

        # Calculate stability (std dev / mean)
        pe_std = float(np.std(pe_list))
        pe_mean = float(np.mean(pe_list))
        stability = 1 - min(1.0, pe_std / pe_mean) if pe_mean > 0 else 0.0

        fair_price = Decimal(str(round(ttm_eps * pe_50, 2)))
        cheap_price = Decimal(str(round(ttm_eps * pe_25, 2)))
        expensive_price = Decimal(str(round(ttm_eps * pe_75, 2)))

        # Confidence based on stability and sample size
        confidence = Decimal(str(round(0.4 + 0.4 * stability, 2)))

        return EstimateResult(
            model_type="pe_band",
            cheap_price=cheap_price,
            fair_price=fair_price,
            expensive_price=expensive_price,
            confidence=confidence,
            details={
                "ttm_eps": round(ttm_eps, 2),
                "pe_median": round(pe_50, 2),
                "pe_std_dev": round(pe_std, 2),
                "stability": round(stability, 2),
                "sample_count": len(pe_list),
            },
        )
