"""FastAPI dependencies specific to /api/v1/institutional/* endpoints.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5 + §9.

Provides:
  - ``get_edgar_client()``       Async context-manager–opened `EdgarClient`
                                  injected into search / refresh
                                  endpoints. Tests override with a
                                  `MockEdgarClient` via
                                  ``app.dependency_overrides[get_edgar_client]``.
  - ``tracked_filers_count_provider``
                                  Async callable for
                                  ``tier_guard(limit_key="max_tracked_filers",
                                  count_provider=...)`` — the dependency
                                  layer first-line defence (spec §9).

Architectural notes:
- The EdgarClient is opened per-request (a fresh `httpx.AsyncClient`
  inside its async context manager) because httpx clients are
  cheap to construct and the rate-limit / retry state is naturally
  scoped to a single request. We may swap to a process-wide singleton
  if Phase 2 shows the overhead matters.
- `tracked_filers_count_provider` mirrors
  `app.api.v1.holdings._count_providers.account_count_provider` — same
  `_session_scope()` workaround for the fact that `tier_guard`'s
  count provider is NOT a FastAPI dependency (it cannot use Depends).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.api.deps import get_db
from app.modules.institutional.edgar_client import EdgarClient
from app.repositories.institutional import F13UserSubscriptionRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


# ── EdgarClient dependency ────────────────────────────────────────────


async def get_edgar_client() -> AsyncIterator[EdgarClient]:
    """Yield an opened `EdgarClient` for the lifetime of the request.

    Production wiring: a fresh httpx-backed client per request. SEC's
    rate-limit subject is the source IP, not the connection, so per-
    request lifecycle is the simplest correct choice for Phase 1.

    Tests override this dependency on the FastAPI app instance::

        app.dependency_overrides[get_edgar_client] = lambda: MockEdgarClient()

    The override yields a single, possibly module-shared mock object
    that already implements the EdgarClient duck-typed contract
    (`search_filers_by_name`, `list_filings_for_filer`,
    `fetch_filing_xml`).
    """
    async with EdgarClient() as client:
        yield client


# ── tier_guard count provider ─────────────────────────────────────────


@asynccontextmanager
async def _session_scope() -> AsyncIterator[AsyncSession]:
    """Open an AsyncSession honouring `app.dependency_overrides` when
    set, otherwise fall back to the production `get_db` generator.

    `tier_guard.current_count_provider` is invoked as a plain async
    callable inside a FastAPI dependency, so it cannot itself use
    `Depends(get_db)`. We replicate the override lookup manually so
    tests pointing at `db_session` continue to work. See
    `app.api.v1.holdings._count_providers` for the exact same pattern.
    """
    try:
        from app.main import app as _app  # local import: break cycles

        override = _app.dependency_overrides.get(get_db)
    except Exception:  # pragma: no cover - defensive
        override = None
    gen_fn = override if override is not None else get_db
    gen = gen_fn()
    try:
        session = await gen.__anext__()
        yield session
    finally:
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


async def _safe_count(coro_factory) -> int:
    """Run a count query and swallow any session / event-loop error.

    `tier_guard` is the FIRST line of defence (spec §9 雙保險). If the
    count query itself fails (e.g. wrong event loop in tests, or a
    transient DB outage), we MUST NOT 500 the request — that would
    block legitimate writes. Returning 0 here makes the dependency a
    no-op and the service layer's mandatory second line re-checks
    against the real request session.
    """
    try:
        return await coro_factory()
    except Exception:  # pragma: no cover - defensive isolation
        return 0


async def tracked_filers_count_provider(*, user: User) -> int:
    """Number of `f13_user_subscriptions` owned by `user` — feeds
    `tier_guard(limit_key="max_tracked_filers", ...)`.

    Bypass / fallback semantics: returns 0 on any error (per
    `_safe_count`) so the dependency layer can never produce a 500.
    The service layer's `_assert_filer_quota` re-checks against the
    request session and raises `F13TierLimitExceeded` if the quota is
    actually exhausted.
    """

    async def _q() -> int:
        async with _session_scope() as session:
            return await F13UserSubscriptionRepo(session).count_by_user(user.id)

    return await _safe_count(_q)


__all__ = [
    "get_edgar_client",
    "tracked_filers_count_provider",
]
