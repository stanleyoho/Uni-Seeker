from fastapi import APIRouter

from app.api.v1.indicators import router as indicators_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.prices import router as prices_router
from app.api.v1.screener import router as screener_router
from app.api.v1.financials import router as financials_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.backtest import router as backtest_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(prices_router)
v1_router.include_router(indicators_router)
v1_router.include_router(screener_router)
v1_router.include_router(notifications_router)
v1_router.include_router(stocks_router)
v1_router.include_router(financials_router)
v1_router.include_router(strategies_router)
v1_router.include_router(backtest_router)
