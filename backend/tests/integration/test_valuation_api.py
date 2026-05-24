from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price_estimate import PriceEstimate
from app.models.stock import Stock


@pytest.mark.asyncio
async def test_get_valuation_estimates_success(
    client: AsyncClient, db_session: AsyncSession, pro_user_token: dict
):
    # 1. Seed a stock
    stock = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
    db_session.add(stock)
    await db_session.flush()

    # 2. Seed price estimates (multiple models to ensure high confidence via convergence)
    today = date.today()
    estimates = [
        PriceEstimate(
            stock_id=stock.id, date=today, model_type="dcf",
            cheap_price=Decimal("800"), fair_price=Decimal("1000"),
            expensive_price=Decimal("1200"), confidence=Decimal("0.6"), details={}
        ),
        PriceEstimate(
            stock_id=stock.id, date=today, model_type="pe_band",
            cheap_price=Decimal("800"), fair_price=Decimal("1000"),
            expensive_price=Decimal("1200"), confidence=Decimal("0.8"), details={}
        ),
        PriceEstimate(
            stock_id=stock.id, date=today, model_type="composite",
            cheap_price=Decimal("800"), fair_price=Decimal("1000"),
            expensive_price=Decimal("1200"), confidence=Decimal("0.7"),
            details={"models_used": ["dcf", "pe_band"], "convergence_score": 1.0}
        )
    ]
    db_session.add_all(estimates)
    await db_session.commit()

    # 3. Test the API
    response = await client.get(
        "/api/v1/valuation/2330.TW/estimates",
        headers=pro_user_token,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "2330.TW"
    # estimates list filters out composite
    assert len(data["estimates"]) == 2
    assert data["latest_composite"]["model_type"] == "composite"
    
    # Verify DecimalStr serialization
    assert float(data["latest_composite"]["fair_price"]) == 1000.0
    assert float(data["latest_composite"]["confidence"]) == 0.7

@pytest.mark.asyncio
async def test_get_valuation_no_data(
    client: AsyncClient, db_session: AsyncSession, pro_user_token: dict
):
    # Seed stock but no estimates
    stock = Stock(symbol="2317.TW", name="Hon Hai", market=Market.TW_TWSE)
    db_session.add(stock)
    await db_session.commit()

    response = await client.get(
        "/api/v1/valuation/2317.TW/estimates",
        headers=pro_user_token,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["estimates"]) == 0
    assert data["latest_composite"] is None
