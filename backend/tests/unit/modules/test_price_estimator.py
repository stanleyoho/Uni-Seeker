import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from app.modules.price_estimator.utils import ValuationUtils
from app.modules.price_estimator.pe_model import PEBandEstimator
from app.modules.price_estimator.dcf import DCFEstimator
from app.modules.price_estimator.composite import CompositeEstimator
from app.modules.price_estimator.base import EstimateResult

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
async def test_composite_divergence_penalty():
    session = AsyncMock()
    
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
