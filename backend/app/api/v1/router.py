from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.company import router as company_router
from app.api.v1.heatmap import router as heatmap_router
from app.api.v1.institutional import router as institutional_router
from app.api.v1.market import router as market_router
from app.api.v1.financials import router as financials_router
from app.api.v1.indicators import router as indicators_router
from app.api.v1.low_base import router as low_base_router
from app.api.v1.margin import router as margin_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.prices import router as prices_router
from app.api.v1.revenue import router as revenue_router
from app.api.v1.screener import router as screener_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.sync import router as sync_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(prices_router)
v1_router.include_router(indicators_router)
v1_router.include_router(screener_router)
v1_router.include_router(notifications_router)
v1_router.include_router(stocks_router)
v1_router.include_router(financials_router)
v1_router.include_router(strategies_router)
v1_router.include_router(backtest_router)
v1_router.include_router(revenue_router)
v1_router.include_router(low_base_router)
v1_router.include_router(margin_router)
v1_router.include_router(company_router)
v1_router.include_router(market_router)
v1_router.include_router(heatmap_router)
v1_router.include_router(institutional_router)
v1_router.include_router(sync_router)
