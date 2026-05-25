from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import StockPrice
from app.models.valuation import StockValuation
from app.modules.price_estimator.base import EstimateResult


class DDMEstimator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def estimate(self, stock_id: int) -> EstimateResult:
        # 1. Fetch latest price and dividend yield to derive DPS
        price_query = (
            select(StockPrice.close)
            .where(StockPrice.stock_id == stock_id)
            .order_by(StockPrice.date.desc())
            .limit(1)
        )
        yield_query = (
            select(StockValuation.dividend_yield)
            .where(StockValuation.stock_id == stock_id)
            .where(StockValuation.dividend_yield is not None)
            .order_by(StockValuation.date.desc())
            .limit(1)
        )

        price_result = await self.session.execute(price_query)
        yield_result = await self.session.execute(yield_query)

        current_price = price_result.scalar_one_or_none()
        div_yield = yield_result.scalar_one_or_none()

        if not current_price or not div_yield or div_yield <= 0:
            return EstimateResult(
                model_type="ddm",
                cheap_price=None,
                fair_price=None,
                expensive_price=None,
                confidence=Decimal("0.0"),
                details={"reason": "No dividend history or yield data"},
            )

        # DPS = Yield * Price / 100 (assuming yield is in percentage points like 4.5)
        dps = float(current_price * div_yield / Decimal("100.0"))

        # 2. Model Parameters (Defaults)
        growth_rate = 0.03  # 3% dividend growth
        required_return = 0.08  # 8% required return (r > g required for Gordon model)

        if required_return <= growth_rate:
            return EstimateResult(
                model_type="ddm",
                cheap_price=None,
                fair_price=None,
                expensive_price=None,
                confidence=Decimal("0.0"),
                details={"reason": "Required return must be greater than growth rate"},
            )

        # 3. Gordon Growth Model Formula: P = D1 / (r - g)
        d1 = dps * (1 + growth_rate)
        fair_price_num = d1 / (required_return - growth_rate)

        fair_price = Decimal(str(round(fair_price_num, 2)))
        cheap_price = Decimal(str(round(fair_price_num * 0.8, 2)))
        expensive_price = Decimal(str(round(fair_price_num * 1.2, 2)))

        return EstimateResult(
            model_type="ddm",
            cheap_price=cheap_price,
            fair_price=fair_price,
            expensive_price=expensive_price,
            confidence=Decimal("0.40"),
            details={
                "derived_dps": round(dps, 2),
                "growth_rate": growth_rate,
                "required_return": required_return,
                "dividend_yield": float(div_yield),
            },
        )
