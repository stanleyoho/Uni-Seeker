
import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.models.price import StockPrice

logger = structlog.get_logger()


class ValuationUtils:
    @staticmethod
    def calculate_cagr(values: list[float]) -> float:
        """Calculate Compound Annual Growth Rate."""
        if not values or len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
            return 0.05  # Default conservative growth

        # values are expected to be in chronological order (oldest first)
        n = len(values) / 4.0  # Assuming quarterly data
        try:
            cagr = (values[-1] / values[0]) ** (1 / n) - 1
            # Clamp growth between 2% and 15% to be realistic
            return max(0.02, min(0.15, cagr))
        except Exception:
            return 0.05

    @staticmethod
    async def get_dynamic_growth_rate(session: AsyncSession, stock_id: int) -> float:
        """Derive growth rate from historical EPS and Revenue."""
        stmt = (
            select(FinancialMetrics.eps)
            .where(FinancialMetrics.stock_id == stock_id)
            .where(FinancialMetrics.eps != None)
            .order_by(FinancialMetrics.period.asc())
            .limit(12)  # Last 3 years
        )
        result = await session.execute(stmt)
        eps_history = [float(row[0]) for row in result.all()]

        return ValuationUtils.calculate_cagr(eps_history)

    @staticmethod
    async def estimate_wacc(session: AsyncSession, stock_id: int) -> float:
        """
        Estimate Weighted Average Cost of Capital (Simplified).
        Base = Risk Free Rate + Beta * Market Risk Premium
        """
        # 1. Simplified Beta calculation (Volatility relative to market)
        # In a real system, we'd compare against an index (like TAIEX)
        # Here we use a proxy based on stock price volatility
        stmt = (
            select(StockPrice.close)
            .where(StockPrice.stock_id == stock_id)
            .order_by(StockPrice.date.desc())
            .limit(250)
        )
        result = await session.execute(stmt)
        prices = [float(row[0]) for row in result.all()]

        if len(prices) < 20:
            return 0.08  # Default 8% for stable TW stocks

        returns = np.diff(np.log(prices))
        volatility = np.std(returns) * np.sqrt(250)

        # Proxy Beta: more volatile stocks get higher discount rates
        # 0.04 (RF) + Beta * 0.06 (Premium)
        # We assume 15% vol is Beta=1.0
        beta = max(0.8, min(2.0, volatility / 0.15))
        wacc = 0.03 + beta * 0.05

        return float(round(wacc, 3))

    @staticmethod
    def clean_outliers(values: list[float]) -> list[float]:
        """Remove extreme outliers using Interquartile Range."""
        if len(values) < 4:
            return values
        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        return [v for v in values if lower <= v <= upper]
