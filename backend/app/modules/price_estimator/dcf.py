from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.models.financial_statement import FinancialStatement
from app.modules.price_estimator.base import EstimateResult
from app.modules.price_estimator.utils import ValuationUtils


class DCFEstimator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def estimate(self, stock_id: int) -> EstimateResult:
        # 1. Fetch latest annual FCF
        fcf_query = (
            select(FinancialMetrics.fcf)
            .where(FinancialMetrics.stock_id == stock_id)
            .where(FinancialMetrics.fcf.is_not(None))
            .order_by(FinancialMetrics.period.desc())
            .limit(4)
        )
        fcf_result = await self.session.execute(fcf_query)
        current_fcf = sum([float(row[0]) for row in fcf_result.all()])

        # 2. Fetch shares outstanding (precise heuristic)
        shares_query = (
            select(FinancialStatement.data)
            .where(FinancialStatement.stock_id == stock_id)
            .where(FinancialStatement.statement_type == "balance")
            .order_by(FinancialStatement.period.desc())
            .limit(1)
        )
        shares_result = await self.session.execute(shares_query)
        latest_bs = shares_result.scalar_one_or_none()

        capital = 0
        if latest_bs:
            # TW SE precise keys
            capital = latest_bs.get(
                "股本", latest_bs.get("普通股股本", latest_bs.get("權益總額", 0))
            )

        shares_outstanding = (capital / 10) if capital > 0 else 0

        if current_fcf <= 0 or shares_outstanding <= 0:
            return EstimateResult(
                model_type="dcf",
                cheap_price=None,
                fair_price=None,
                expensive_price=None,
                confidence=Decimal("0.0"),
                details={"reason": "Negative FCF or invalid share count"},
            )

        # 3. Dynamic Parameters
        growth_rate = await ValuationUtils.get_dynamic_growth_rate(self.session, stock_id)
        discount_rate = await ValuationUtils.estimate_wacc(self.session, stock_id)
        terminal_growth = 0.02
        projection_years = 5

        # 4. Two-Stage DCF Calculation
        pv_fcf = 0.0
        fcf_projection = current_fcf
        for t in range(1, projection_years + 1):
            fcf_projection *= 1 + growth_rate
            pv_fcf += fcf_projection / ((1 + discount_rate) ** t)

        terminal_value = (fcf_projection * (1 + terminal_growth)) / (
            discount_rate - terminal_growth
        )
        pv_terminal = terminal_value / ((1 + discount_rate) ** projection_years)

        total_value = pv_fcf + pv_terminal
        fair_price_num = total_value / shares_outstanding

        # 5. Sanity Check (Validation)
        # If fair price is 10x current price, something is wrong with inputs
        # But we handle this in composite.

        fair_price = Decimal(str(round(fair_price_num, 2)))
        cheap_price = Decimal(str(round(fair_price_num * 0.7, 2)))
        expensive_price = Decimal(str(round(fair_price_num * 1.3, 2)))

        return EstimateResult(
            model_type="dcf",
            cheap_price=cheap_price,
            fair_price=fair_price,
            expensive_price=expensive_price,
            confidence=Decimal("0.60"),
            details={
                "current_fcf": round(current_fcf, 2),
                "growth_rate": round(growth_rate, 4),
                "discount_rate": round(discount_rate, 4),
                "terminal_growth": terminal_growth,
                "pv_fcf": round(pv_fcf, 2),
                "pv_terminal": round(pv_terminal, 2),
                "shares_outstanding": int(shares_outstanding),
            },
        )
