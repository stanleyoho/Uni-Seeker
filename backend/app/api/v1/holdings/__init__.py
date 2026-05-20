"""Portfolio Tracker HTTP layer (UNI-PORT-001 Batch D).

Spec §5.4. Mounts four sub-routers under a shared `/holdings` prefix:

    accounts.py   POST/GET/PATCH/DELETE  /holdings/accounts(/{id})
    trades.py     POST/GET/PATCH/DELETE  /holdings/trades(/{id})
    positions.py  GET                    /holdings/positions(/{aid}/{sym})
    summary.py    GET                    /holdings/summary(/{aid})

`/holdings` was chosen over `/portfolio` because the latter is already
mounted (`app/api/v1/portfolio.py`) for the backtest portfolio.
See spec §5.4 + Q14.2 for the rationale.

Each sub-router is fully self-contained — endpoints translate domain
exceptions from `app.services.portfolio.*` into HTTP status codes
defined in `app.api.v1.holdings._detail` (single source of truth for
the `detail=` strings the frontend asserts on).
"""
from fastapi import APIRouter

from app.api.v1.holdings.accounts import router as accounts_router
from app.api.v1.holdings.positions import router as positions_router
from app.api.v1.holdings.summary import router as summary_router
from app.api.v1.holdings.trades import router as trades_router

router = APIRouter(prefix="/holdings", tags=["holdings"])
router.include_router(accounts_router)
router.include_router(trades_router)
router.include_router(positions_router)
router.include_router(summary_router)

__all__ = ["router"]
