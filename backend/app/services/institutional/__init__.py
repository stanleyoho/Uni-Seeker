"""Institutional 13F services (Phase 1 / UNI-F13-001 Batch B2).

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5 (layering), §6.2 (service breakdown), §9 (tier double guard).

Service layer orchestrates `app.repositories.institutional.*` (CRUD) +
`app.modules.institutional.*` (pure EDGAR / parser / diff) behind a
transaction boundary. Same anti-coupling guarantees as
`app.services.portfolio`:

- R2: no raw SQL here — every DB touch goes through a repo.
- R3 (mirror): no XML parsing / diff math here — every computation
  goes through a domain module.
- R5: services receive an `AsyncSession` injected by the API layer;
  they never create their own DB session.

Tier enforcement (spec §9 double guard):
- Endpoint `tier_guard(...)` is the first line (Batch C).
- Service-level assertions (`_assert_filer_quota`,
  `_assert_feature`) are the second line — they raise
  `F13TierLimitExceeded` / `F13TierFeatureUnavailable` domain
  exceptions for the API layer to translate to HTTP 403.
"""
from app.services.institutional.cross_stock_service import (
    F13CrossStockService,
)
from app.services.institutional.exceptions import (
    F13EdgarError,
    F13FilerNotFound,
    F13FilingNotFound,
    F13RefreshInFlight,
    F13ServiceError,
    F13SubscriptionExists,
    F13TierFeatureUnavailable,
    F13TierLimitExceeded,
)
from app.services.institutional.filer_search_service import (
    F13FilerSearchService,
)
from app.services.institutional.filing_service import F13FilingService
from app.services.institutional.subscription_service import (
    F13SubscriptionService,
)

__all__ = [
    # services
    "F13CrossStockService",
    "F13FilerSearchService",
    "F13FilingService",
    "F13SubscriptionService",
    # exceptions
    "F13EdgarError",
    "F13FilerNotFound",
    "F13FilingNotFound",
    "F13RefreshInFlight",
    "F13ServiceError",
    "F13SubscriptionExists",
    "F13TierFeatureUnavailable",
    "F13TierLimitExceeded",
]
