from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metrics import FinancialMetrics
from app.models.industry import Industry
from app.models.industry_metrics import IndustryMetrics
from app.models.stock import Stock
from app.models.valuation import StockValuation
from app.modules.industry.aggregator import IndustryAggregator


@pytest.mark.asyncio
async def test_aggregate_industry(db_session: AsyncSession):
    # 1. Setup Data
    industry = Industry(name="Semiconductors")
    db_session.add(industry)
    await db_session.flush()

    stock1 = Stock(symbol="2330", name="TSMC", market="TWSE", industry_id=industry.id)
    stock2 = Stock(symbol="2454", name="MediaTek", market="TWSE", industry_id=industry.id)
    db_session.add_all([stock1, stock2])
    await db_session.flush()

    # Quarterly Metrics for 2024-Q1
    m1 = FinancialMetrics(
        stock_id=stock1.id,
        period="2024-Q1",
        roe=30.0,
        gross_margin=50.0,
        fiscal_year=2024,
        fiscal_quarter=1,
    )
    m2 = FinancialMetrics(
        stock_id=stock2.id,
        period="2024-Q1",
        roe=20.0,
        gross_margin=40.0,
        fiscal_year=2024,
        fiscal_quarter=1,
    )
    db_session.add_all([m1, m2])

    # Valuations (Daily)
    v1 = StockValuation(
        stock_id=stock1.id,
        date=date(2024, 3, 31),
        pe_ratio=25.0,
        pb_ratio=5.0,
        dividend_yield=2.5,
    )
    v2 = StockValuation(
        stock_id=stock2.id,
        date=date(2024, 3, 31),
        pe_ratio=15.0,
        pb_ratio=3.0,
        dividend_yield=3.5,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()

    # 2. Run Aggregator
    aggregator = IndustryAggregator(db_session)
    await aggregator.aggregate_all_industries("2024-Q1")

    # 3. Verify Results
    result = await db_session.execute(
        select(IndustryMetrics).where(IndustryMetrics.industry_id == industry.id)
    )
    metric = result.scalars().first()

    assert metric is not None
    assert metric.period == "2024-Q1"
    # Medians:
    # ROE: (30 + 20) / 2 = 25.0
    # Gross Margin: (50 + 40) / 2 = 45.0
    # PE: (25 + 15) / 2 = 20.0
    # PB: (5 + 3) / 2 = 4.0
    # Yield: (2.5 + 3.5) / 2 = 3.0
    assert metric.median_roe == 25.0
    assert metric.median_gross_margin == 45.0
    assert metric.median_pe == 20.0
    assert metric.median_pb == 4.0
    assert metric.median_yield == 3.0


@pytest.mark.asyncio
async def test_aggregate_industry_updates_existing(db_session: AsyncSession):
    industry = Industry(name="Tech")
    db_session.add(industry)
    await db_session.flush()

    # Pre-existing metric
    existing = IndustryMetrics(industry_id=industry.id, period="2024-Q1", median_pe=10.0)
    db_session.add(existing)
    await db_session.flush()

    stock = Stock(symbol="S1", name="S1", market="TWSE", industry_id=industry.id)
    db_session.add(stock)
    await db_session.flush()

    val = StockValuation(stock_id=stock.id, date=date(2024, 3, 31), pe_ratio=20.0)
    db_session.add(val)
    await db_session.flush()

    aggregator = IndustryAggregator(db_session)
    await aggregator.aggregate_all_industries("2024-Q1")

    # Verify update
    await db_session.refresh(existing)
    assert existing.median_pe == 20.0
