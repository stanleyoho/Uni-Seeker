from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.price_estimator.base import EstimateResult
from app.modules.price_estimator.composite import CompositeEstimator
from app.modules.price_estimator.dcf import DCFEstimator
from app.modules.price_estimator.ddm import DDMEstimator
from app.modules.price_estimator.pe_model import PEBandEstimator
from app.modules.price_estimator.utils import ValuationUtils

# --- Utils Tests ---

def test_calculate_cagr():
    # Scenario 1: Steady growth 100 -> 121 over 2 years (8 quarters)
    # (121/100)^(1/2) - 1 = 0.1 (10%)
    values = [100.0] * 4 + [121.0] * 4
    cagr = ValuationUtils.calculate_cagr(values)
    assert round(cagr, 2) == 0.10

    # Scenario 2: Hyper growth (clamped to 15%)
    values = [1.0, 100.0]
    cagr = ValuationUtils.calculate_cagr(values)
    assert cagr == 0.15

    # Scenario 3: Negative/Zero values (fallback to 5%)
    assert ValuationUtils.calculate_cagr([0, 100]) == 0.05
    assert ValuationUtils.calculate_cagr([-10, 100]) == 0.05

def test_clean_outliers():
    data = [10, 12, 11, 13, 100, 9] # 100 is outlier
    cleaned = ValuationUtils.clean_outliers(data)
    assert 100 not in cleaned
    assert 12 in cleaned

# --- Model Tests (Mocks) ---

@pytest.mark.asyncio
async def test_pe_band_logic():
    session = AsyncMock()
    
    # Mock PE ratios: 25 samples
    pe_ratios = [15.0] * 25
    pe_results = MagicMock()
    pe_results.all.return_value = [(p,) for p in pe_ratios]
    
    # Mock EPS: [1, 1, 1, 1] -> TTM 4
    eps_results = MagicMock()
    eps_results.all.return_value = [(1.0,), (1.0,), (1.0,), (1.0,)]
    
    session.execute.side_effect = [pe_results, eps_results]
    
    estimator = PEBandEstimator(session)
    res = await estimator.estimate(1)
    
    # Fair = 4 * 15 = 60
    assert float(res.fair_price) == 60.0
    assert res.confidence > 0.5

@pytest.mark.asyncio
async def test_pe_band_insufficient_data():
    """Edge: <20 samples -> confidence 0, no fair price."""
    session = AsyncMock()

    pe_results = MagicMock()
    pe_results.all.return_value = [(15.0,)] * 5  # only 5 samples
    eps_results = MagicMock()
    eps_results.all.return_value = [(1.0,)] * 4

    session.execute.side_effect = [pe_results, eps_results]

    estimator = PEBandEstimator(session)
    res = await estimator.estimate(1)

    assert res.confidence == Decimal("0.0")
    assert res.fair_price is None


@pytest.mark.asyncio
async def test_ddm_happy_path():
    """DDM: price=100, yield=4 -> DPS=4, fair = 4*1.03/(0.08-0.03) = 82.4."""
    session = AsyncMock()

    price_res = MagicMock()
    price_res.scalar_one_or_none.return_value = Decimal("100.0")
    yield_res = MagicMock()
    yield_res.scalar_one_or_none.return_value = Decimal("4.0")

    session.execute.side_effect = [price_res, yield_res]

    estimator = DDMEstimator(session)
    res = await estimator.estimate(1)

    assert res.model_type == "ddm"
    assert res.fair_price is not None
    assert float(res.fair_price) == pytest.approx(82.4, abs=0.5)
    assert res.cheap_price < res.fair_price < res.expensive_price


@pytest.mark.asyncio
async def test_ddm_no_dividend_yield():
    """Edge: no dividend yield available -> confidence 0."""
    session = AsyncMock()

    price_res = MagicMock()
    price_res.scalar_one_or_none.return_value = Decimal("100.0")
    yield_res = MagicMock()
    yield_res.scalar_one_or_none.return_value = None  # no yield data

    session.execute.side_effect = [price_res, yield_res]

    estimator = DDMEstimator(session)
    res = await estimator.estimate(1)

    assert res.confidence == Decimal("0.0")
    assert res.fair_price is None


@pytest.mark.asyncio
async def test_dcf_negative_fcf():
    """Edge: negative FCF -> confidence 0 (sanity gate)."""
    session = AsyncMock()

    fcf_res = MagicMock()
    fcf_res.all.return_value = [(-1000.0,), (-500.0,)]  # negative FCF
    bs_res = MagicMock()
    bs_res.scalar_one_or_none.return_value = {"股本": 1_000_000}

    session.execute.side_effect = [fcf_res, bs_res]

    estimator = DCFEstimator(session)
    res = await estimator.estimate(1)

    assert res.confidence == Decimal("0.0")
    assert res.fair_price is None


@pytest.mark.asyncio
async def test_composite_returns_none_when_all_models_fail():
    """Edge: every estimator throws -> calculate_and_save returns None gracefully."""
    session = AsyncMock()

    price_res = MagicMock()
    price_res.scalar_one_or_none.return_value = Decimal("100.0")
    session.execute.return_value = price_res

    estimator = CompositeEstimator(session)
    failing = AsyncMock()
    failing.estimate.side_effect = RuntimeError("boom")
    estimator.estimators = [failing, failing, failing]

    res = await estimator.calculate_and_save(1)
    assert res is None


@pytest.mark.asyncio
async def test_composite_divergence_penalty():
    session = AsyncMock()
    session.add = MagicMock()  # SQLAlchemy add() is sync — keep it sync to avoid unawaited-coroutine RuntimeWarning

    # Mock current price = 100
    price_res = MagicMock()
    price_res.scalar_one_or_none.return_value = 100.0
    session.execute.return_value = price_res

    estimator = CompositeEstimator(session)
    
    # Mock two models with wildly different results
    m1 = EstimateResult("m1", Decimal("80"), Decimal("100"), Decimal("120"), Decimal("0.8"))
    m2 = EstimateResult("m2", Decimal("400"), Decimal("500"), Decimal("600"), Decimal("0.8"))
    
    # Patch estimators to return our results
    estimator.estimators = [AsyncMock(), AsyncMock()]
    estimator.estimators[0].estimate.return_value = m1
    estimator.estimators[1].estimate.return_value = m2
    
    res = await estimator.calculate_and_save(1)
    
    # Fair price should be average (100 + 500)/2 = 300
    # But because 100 and 500 are divergent, convergence_score will be low
    # And because 300 is 3x the current price (100), market penalty applies
    assert res.model_type == "composite"
    assert res.confidence < 0.3 # Heavily penalized
