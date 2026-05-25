from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import StockPrice
from app.models.price_estimate import PriceEstimate
from app.modules.price_estimator.base import EstimateResult, PriceEstimator
from app.modules.price_estimator.dcf import DCFEstimator
from app.modules.price_estimator.ddm import DDMEstimator
from app.modules.price_estimator.pe_model import PEBandEstimator
from app.obs.logging import get_logger

logger = get_logger(component="price_estimator")


class CompositeEstimator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.estimators: list[PriceEstimator] = [
            PEBandEstimator(session),
            DCFEstimator(session),
            DDMEstimator(session),
        ]

    async def calculate_and_save(self, stock_id: int) -> PriceEstimate | None:
        # Fetch current price for validation
        price_stmt = (
            select(StockPrice.close)
            .where(StockPrice.stock_id == stock_id)
            .order_by(StockPrice.date.desc())
            .limit(1)
        )
        price_res = await self.session.execute(price_stmt)
        current_price = price_res.scalar_one_or_none()

        results: list[EstimateResult] = []
        for estimator in self.estimators:
            try:
                res = await estimator.estimate(stock_id)
                results.append(res)
            except Exception as e:
                logger.warning(
                    "price_estimator.submodel_failed",
                    estimator=estimator.__class__.__name__,
                    stock_id=stock_id,
                    error=str(e),
                    exc_info=True,
                )

        if not results:
            return None

        today_date = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
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
        # Narrow `fair_price` to non-None up-front so downstream arithmetic
        # operates on Decimal (not Decimal | None).
        valid_results: list[tuple[EstimateResult, Decimal]] = [
            (r, r.fair_price) for r in results if r.fair_price is not None and r.confidence > 0
        ]

        if not valid_results:
            await self.session.commit()
            return None

        # 2.1 Calculate Convergence (Standard Deviation between models)
        fair_prices = [float(fp) for _, fp in valid_results]
        if len(fair_prices) > 1:
            mean_fair = sum(fair_prices) / len(fair_prices)
            variance = sum((p - mean_fair) ** 2 for p in fair_prices) / len(fair_prices)
            std_dev = variance**0.5
            convergence_penalty = max(0, 1 - (std_dev / mean_fair)) if mean_fair > 0 else 0
        else:
            convergence_penalty = 0.5  # Only one model worked

        # 2.2 Calculate Weighted Averages — explicit Decimal(0) start to keep
        # sum() return type Decimal (default int start otherwise widens to
        # Decimal | int and pollutes downstream arithmetic).
        total_conf = sum((r.confidence for r, _ in valid_results), Decimal(0))
        comp_fair = (
            sum((fp * r.confidence for r, fp in valid_results), Decimal(0)) / total_conf
        )
        comp_cheap = (
            sum(((r.cheap_price or fp) * r.confidence for r, fp in valid_results), Decimal(0))
            / total_conf
        )
        comp_expensive = (
            sum(
                ((r.expensive_price or fp) * r.confidence for r, fp in valid_results),
                Decimal(0),
            )
            / total_conf
        )

        # 2.3 Market Context Validation
        # If the gap between composite and current market price is insane, drop confidence
        final_confidence = (total_conf / len(self.estimators)) * Decimal(
            str(round(convergence_penalty, 2))
        )

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
                "models_used": [r.model_type for r, _ in valid_results],
                "convergence_score": round(convergence_penalty, 2),
                "model_prices": {r.model_type: float(fp) for r, fp in valid_results},
            },
        )
        self.session.add(composite)
        await self.session.commit()
        return composite
