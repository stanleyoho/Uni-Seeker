from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_estimate import PriceEstimate
from app.models.price import StockPrice
from app.modules.price_estimator.base import EstimateResult
from app.modules.price_estimator.dcf import DCFEstimator
from app.modules.price_estimator.ddm import DDMEstimator
from app.modules.price_estimator.pe_model import PEBandEstimator


class CompositeEstimator:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.estimators = [
            PEBandEstimator(session),
            DCFEstimator(session),
            DDMEstimator(session),
        ]

    async def calculate_and_save(self, stock_id: int) -> PriceEstimate | None:
        # Fetch current price for validation
        price_stmt = select(StockPrice.close).where(StockPrice.stock_id == stock_id).order_by(StockPrice.date.desc()).limit(1)
        price_res = await self.session.execute(price_stmt)
        current_price = price_res.scalar_one_or_none()
        
        results: list[EstimateResult] = []
        for estimator in self.estimators:
            try:
                res = await estimator.estimate(stock_id)
                results.append(res)
            except Exception as e:
                print(f"Error in {estimator.__class__.__name__}: {e}")

        if not results:
            return None

        today_date = date.today()
        await self.session.execute(
            delete(PriceEstimate).where(
                PriceEstimate.stock_id == stock_id, PriceEstimate.date == today_date
            )
        )

        # 1. Individual Estimates Storage
        for res in results:
            est = PriceEstimate(
                stock_id=stock_id,
                date=today_date,
                model_type=res.model_type,
                cheap_price=res.cheap_price,
                fair_price=res.fair_price,
                expensive_price=res.expensive_price,
                confidence=res.confidence,
                details=res.details,
            )
            self.session.add(est)

        # 2. Advanced Validation & Blending
        valid_results = [
            r for r in results if r.fair_price is not None and r.confidence > 0
        ]

        if not valid_results:
            await self.session.commit()
            return None

        # 2.1 Calculate Convergence (Standard Deviation between models)
        fair_prices = [float(r.fair_price) for r in valid_results]
        if len(fair_prices) > 1:
            mean_fair = sum(fair_prices) / len(fair_prices)
            variance = sum((p - mean_fair) ** 2 for p in fair_prices) / len(fair_prices)
            std_dev = variance ** 0.5
            convergence_penalty = max(0, 1 - (std_dev / mean_fair)) if mean_fair > 0 else 0
        else:
            convergence_penalty = 0.5  # Only one model worked

        # 2.2 Calculate Weighted Averages
        total_conf = sum(r.confidence for r in valid_results)
        comp_fair = sum(r.fair_price * r.confidence for r in valid_results) / total_conf
        comp_cheap = sum((r.cheap_price or r.fair_price) * r.confidence for r in valid_results) / total_conf
        comp_expensive = sum((r.expensive_price or r.fair_price) * r.confidence for r in valid_results) / total_conf
        
        # 2.3 Market Context Validation
        # If the gap between composite and current market price is insane, drop confidence
        final_confidence = (total_conf / len(self.estimators)) * Decimal(str(round(convergence_penalty, 2)))
        
        if current_price:
            diff_ratio = abs(float(comp_fair) - float(current_price)) / float(current_price)
            if diff_ratio > 1.5:  # 150% difference
                final_confidence *= Decimal("0.5")
            elif diff_ratio > 3.0:
                final_confidence *= Decimal("0.1")

        composite = PriceEstimate(
            stock_id=stock_id,
            date=today_date,
            model_type="composite",
            cheap_price=comp_cheap,
            fair_price=comp_fair,
            expensive_price=comp_expensive,
            confidence=min(Decimal("1.0"), final_confidence),
            details={
                "models_used": [r.model_type for r in valid_results],
                "convergence_score": round(convergence_penalty, 2),
                "model_prices": {r.model_type: float(r.fair_price) for r in valid_results}
            },
        )
        self.session.add(composite)
        await self.session.commit()
        return composite
