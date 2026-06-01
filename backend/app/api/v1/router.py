from fastapi import APIRouter

from app.api.v1.ai_commentary import router as ai_commentary_router
from app.api.v1.alpha import router as alpha_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.backtest_jobs import router as backtest_jobs_router
from app.api.v1.billing import router as billing_router
from app.api.v1.company import router as company_router
from app.api.v1.etf_arbitrage import router as etf_arbitrage_router
from app.api.v1.financial_metrics import router as financial_metrics_router
from app.api.v1.financials import router as financials_router
from app.api.v1.heatmap import router as heatmap_router
from app.api.v1.holdings import router as holdings_router
from app.api.v1.indicators import router as indicators_router
from app.api.v1.institutional import router as institutional_router
from app.api.v1.journal import router as journal_router
from app.api.v1.low_base import router as low_base_router
from app.api.v1.macro import router as macro_router
from app.api.v1.margin import router as margin_router
from app.api.v1.market import router as market_router
from app.api.v1.me_audit import router as me_audit_router
from app.api.v1.me_notifications import router as me_notifications_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.prices import router as prices_router
from app.api.v1.revenue import router as revenue_router
from app.api.v1.scanner import router as scanner_router
from app.api.v1.screener import router as screener_router
from app.api.v1.signals import router as signals_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.sync import router as sync_router
from app.api.v1.tw_institutional import router as tw_institutional_router
from app.api.v1.valuation_models import router as valuation_models_router
from app.api.v1.watchlist import router as watchlist_router
from app.api.v1.ws import router as ws_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(onboarding_router)
v1_router.include_router(prices_router)
v1_router.include_router(indicators_router)
v1_router.include_router(screener_router)
v1_router.include_router(notifications_router)
v1_router.include_router(me_notifications_router)
v1_router.include_router(me_audit_router)
v1_router.include_router(alpha_router)
v1_router.include_router(stocks_router)
# Nested under /stocks/{symbol}/ai-commentary — register after stocks_router
# so FastAPI's path matcher resolves cleanly.
v1_router.include_router(ai_commentary_router)
v1_router.include_router(financial_metrics_router)
v1_router.include_router(financials_router)
v1_router.include_router(strategies_router)
v1_router.include_router(backtest_router)
v1_router.include_router(revenue_router)
v1_router.include_router(low_base_router)
v1_router.include_router(margin_router)
v1_router.include_router(company_router)
v1_router.include_router(market_router)
v1_router.include_router(macro_router)
v1_router.include_router(heatmap_router)
v1_router.include_router(institutional_router)
v1_router.include_router(journal_router)
v1_router.include_router(holdings_router)
v1_router.include_router(sync_router)
v1_router.include_router(valuation_models_router)
v1_router.include_router(backtest_jobs_router)
v1_router.include_router(portfolio_router)
v1_router.include_router(scanner_router)
v1_router.include_router(signals_router)
v1_router.include_router(tw_institutional_router)
v1_router.include_router(predictions_router)
v1_router.include_router(billing_router)
v1_router.include_router(watchlist_router)
v1_router.include_router(etf_arbitrage_router)
v1_router.include_router(ws_router)
