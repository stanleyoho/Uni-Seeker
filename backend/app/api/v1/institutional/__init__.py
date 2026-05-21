"""Institutional 13F Holdings Tracker HTTP layer (Phase 1 Batch C).

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5.

Mounts four sub-routers under a shared `/institutional` prefix:

    filers.py    POST/GET/DELETE  /institutional/filers(/{id})
                                  /institutional/filers/search
                                  /institutional/filers/{id}/refresh
    filings.py   GET              /institutional/filers/{id}/filings
                                  /institutional/filers/{id}/holdings
                                  /institutional/filers/{id}/diff
    stocks.py    GET              /institutional/stocks/{symbol}/institutional
    legacy.py    GET              /institutional/{symbol}    (FinMind TW data)

Mount order matters — `legacy.py`'s `/{symbol}` is a catch-all under
the same prefix, so the more specific 13F routers MUST be included
first or `/filers` etc. would be matched as `{symbol}="filers"`.

Each sub-router translates `app.services.institutional` domain
exceptions into HTTP status codes defined in
`app.api.v1.institutional._detail`.
"""
from fastapi import APIRouter

from app.api.v1.institutional.filers import router as filers_router
from app.api.v1.institutional.filings import router as filings_router
from app.api.v1.institutional.legacy import router as legacy_router
from app.api.v1.institutional.stocks import router as stocks_router

router = APIRouter(prefix="/institutional", tags=["institutional"])

# Specific paths first — preserved /institutional/filers* etc.
router.include_router(filers_router)
router.include_router(filings_router)
router.include_router(stocks_router)
# Legacy catch-all LAST so /{symbol} doesn't eat /filers.
router.include_router(legacy_router)

__all__ = ["router"]
