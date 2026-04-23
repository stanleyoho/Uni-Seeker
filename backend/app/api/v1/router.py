from fastapi import APIRouter

from app.api.v1.indicators import router as indicators_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.prices import router as prices_router
from app.api.v1.screener import router as screener_router
from app.api.v1.stocks import router as stocks_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(prices_router)
v1_router.include_router(indicators_router)
v1_router.include_router(screener_router)
v1_router.include_router(notifications_router)
v1_router.include_router(stocks_router)
