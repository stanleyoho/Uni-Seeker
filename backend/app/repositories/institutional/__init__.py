"""Institutional 13F repositories (Phase 1 / UNI-F13-001 Batch B1).

CRUD-only layer over `app.db.models.institutional.*`. Per spec §5 +
§11 the repos MUST NOT contain business logic (tier checks, EDGAR
fetch, refresh orchestration). Those belong to the service layer.

User isolation per table:

- `F13FilerRepo`            — **shared resource (Q2)**: no `user_id`
                              filter. Filer rows are public; access
                              control lives in the subscription table.
- `F13UserSubscriptionRepo` — **structural** `user_id` filter on every
                              method. This is the only F13 table that
                              carries the user dimension.
- `F13FilingRepo`           — no `user_id` filter (filings hang off the
                              filer). Service layer enforces access via
                              `is_subscribed(user_id, filer_id)`.
- `F13HoldingRepo`          — no `user_id` filter (holdings hang off
                              filings). Cross-filer views (Pro tier
                              `institutional_ownership_panel`) gate at
                              the service layer.
"""
# Eagerly load `app.models` so that the package fully initialises before
# any of our `app.db.models.institutional.*` leaf imports trigger
# `app.models.base`. Without this, a fresh import that enters via the
# repositories path races with `app.models/__init__.py`'s own
# institutional re-export and explodes with a circular ImportError —
# same gotcha that `app.repositories.portfolio` works around.
from app import models as _app_models  # noqa: F401
from app.repositories.institutional.filer_repo import F13FilerRepo
from app.repositories.institutional.filing_repo import F13FilingRepo
from app.repositories.institutional.holding_repo import F13HoldingRepo
from app.repositories.institutional.subscription_repo import (
    F13UserSubscriptionRepo,
)

__all__ = [
    "F13FilerRepo",
    "F13FilingRepo",
    "F13HoldingRepo",
    "F13UserSubscriptionRepo",
]
