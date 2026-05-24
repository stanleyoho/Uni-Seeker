"""Domain exceptions raised by institutional 13F services.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§9, §11 R2.

Services raise domain exceptions, NEVER `HTTPException`. The API layer
(Batch C) catches and translates to HTTP status codes. This keeps
services callable from non-HTTP contexts (CLI, batch jobs, tests)
without importing FastAPI.

Mirrors the `app.services.portfolio.exceptions` module's shape: one
base exception, then a tree of typed subclasses with stable
attribute names that the API layer can read in its exception handlers.
"""

from __future__ import annotations


class F13ServiceError(Exception):
    """Base class for all institutional / 13F service-level domain errors."""


class F13FilerNotFound(F13ServiceError):
    """Filer id does not exist in `f13_filers`.

    Distinct from "filer exists but the user is not subscribed" — that
    case is also surfaced as `F13FilerNotFound` from the service layer
    on purpose, because leaking "exists but not yours" is itself
    information disclosure (same convention as
    `PortfolioAccountNotFound`). API layer translates to 404.
    """


class F13FilingNotFound(F13ServiceError):
    """Filing id / period does not exist (or filer not accessible).

    Same 404/403 collapse as `F13FilerNotFound`. API layer → 404.
    """


class F13SubscriptionExists(F13ServiceError):
    """A subscription for (user_id, filer_id) already exists.

    The UNIQUE constraint on (user_id, filer_id) would catch a duplicate
    INSERT at the DB layer, but services check first so the API layer
    can return a clean 409 Conflict instead of a 500 from
    IntegrityError. Carries the filer_id for the API to include in the
    body if it wants.
    """

    def __init__(self, filer_id: int) -> None:
        self.filer_id = filer_id
        super().__init__(f"already subscribed to filer_id={filer_id}")


class F13RefreshInFlight(F13ServiceError):
    """Concurrent refresh attempted on the same filer.

    Service-side anti-concurrency. We hold a process-local
    `asyncio.Lock` per filer_id (see `F13FilingService._locks`) and
    raise this when the lock is already held by another coroutine.
    API layer translates to 429 Too Many Requests.
    """

    def __init__(self, filer_id: int) -> None:
        self.filer_id = filer_id
        super().__init__(f"refresh in flight for filer_id={filer_id}")


class F13EdgarError(F13ServiceError):
    """Wraps an `EdgarTransientError` (or other EDGAR failure) at the
    service boundary so the API layer can return a 502 / 503 without
    importing the domain client's exception type.

    `edgar_status` carries the upstream HTTP status when known (None
    when the failure was a transport-level timeout).
    """

    def __init__(self, message: str, edgar_status: int | None = None) -> None:
        self.edgar_status = edgar_status
        super().__init__(message)


class F13TierFeatureUnavailable(F13ServiceError):
    """User's tier does not have the requested boolean feature flag.

    Distinct from the portfolio module's `TierFeatureUnavailable` so
    each module's API layer can attach its own error-detail prefix
    without cross-module imports. Keep `feature` attribute name in
    parity for shared exception handlers in Batch C.
    """

    def __init__(self, feature: str) -> None:
        self.feature = feature
        super().__init__(f"tier feature '{feature}' is unavailable")


class F13TierLimitExceeded(F13ServiceError):
    """User's tier numeric quota would be exceeded by this operation.

    Mirrors `app.services.portfolio.exceptions.TierLimitExceeded` so
    the cross-module API exception handler (Batch C) can treat both
    families uniformly when convenient.
    """

    def __init__(self, limit_key: str, current: int, limit: int) -> None:
        self.limit_key = limit_key
        self.current = current
        self.limit = limit
        super().__init__(f"tier limit '{limit_key}' exceeded: {current} >= {limit}")


__all__ = [
    "F13EdgarError",
    "F13FilerNotFound",
    "F13FilingNotFound",
    "F13RefreshInFlight",
    "F13ServiceError",
    "F13SubscriptionExists",
    "F13TierFeatureUnavailable",
    "F13TierLimitExceeded",
]
