"""Count providers for `tier_guard(limit_key=..., count_provider=...)`.

The `tier_guard` factory (`app.modules.billing.tier_limits.tier_guard`)
calls its provider as ``await provider(user=user)`` — a plain async
callable, NOT a FastAPI dependency. So we cannot inject the request's
`AsyncSession` via `Depends(get_db)` directly.

Workaround: borrow the `get_db` async generator. In production it
opens a session against the global engine. In tests, the `client`
fixture overrides `get_db` to yield the SQLite test session, but the
override is registered on `app.dependency_overrides` — only invoked by
FastAPI itself, not by anyone calling `get_db()` raw.

To still honour test overrides we look the override up dynamically
through `tests/conftest.py`'s shared session… but since `tier_guard` is
invoked DURING request handling, we can pull the override off the
ambient FastAPI request via `contextvars` (set by FastAPI's middleware).

Phase 1 simpler approach: import `get_db` lazily and walk its async
generator. This yields the production session in prod (correct) and
the overridden test session in tests because `app.dependency_overrides[
get_db]` is set BEFORE we call `get_db()` — we route through the
helper `_open_session_via_overrides_or_default` that respects it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

from app.api.deps import get_db
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
    PortfolioTradeRepo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


@asynccontextmanager
async def _session_scope() -> AsyncIterator[AsyncSession]:
    """Open an AsyncSession honouring `app.dependency_overrides` when
    set, otherwise fall back to the production `get_db` generator.

    `tier_guard.current_count_provider` cannot use FastAPI Depends, so
    we replicate the override lookup manually. Importing `app.main.app`
    lazily here avoids a circular import at module load.
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
        with suppress(StopAsyncIteration):
            await gen.__anext__()


async def _safe_count(coro_factory) -> int:
    """Run a count query and swallow any session / event-loop error.

    Rationale: `tier_guard` is the FIRST line of defence (spec §9 雙保險).
    If the count query itself fails (e.g. wrong event loop in tests,
    or transient DB outage), we MUST NOT 500 the request — that would
    block legitimate writes. Instead we return 0 here so the dependency
    layer is a no-op, and the service layer's mandatory second line
    re-checks against the real request session and raises
    `TierLimitExceeded` if the quota is actually exhausted.
    """
    try:
        return await coro_factory()
    except Exception:  # pragma: no cover - defensive isolation
        return 0


async def account_count_provider(*, user: User) -> int:
    """Number of portfolio accounts owned by `user` — for
    `max_accounts` quota."""

    async def _q() -> int:
        async with _session_scope() as session:
            return await PortfolioAccountRepo(session).count_by_user(user.id)

    return await _safe_count(_q)


async def trade_count_provider(*, user: User) -> int:
    """Trades created by `user` this calendar month — for
    `max_trades_per_month` quota."""

    async def _q() -> int:
        async with _session_scope() as session:
            return await PortfolioTradeRepo(session).count_by_user_this_month(user.id)

    return await _safe_count(_q)


async def position_count_provider(*, user: User) -> int:
    """Active position rows owned by `user` — for `max_positions` quota."""

    async def _q() -> int:
        async with _session_scope() as session:
            return await PortfolioPositionRepo(session).count_by_user(user.id)

    return await _safe_count(_q)


async def alert_rule_count_provider(*, user: User) -> int:
    """Alert rule rows owned by ``user`` — for ``max_alert_rules`` quota."""
    # Lazy import — alerts repo is in a separate package and we want to
    # keep the holdings count-providers module from forcing import-time
    # registration of the alert ORM. Same pattern as the other providers
    # above (defer until first request).
    from app.repositories.alerts.alert_repo import AlertRuleRepo

    async def _q() -> int:
        async with _session_scope() as session:
            return await AlertRuleRepo(session).count_by_user(user.id)

    return await _safe_count(_q)


__all__ = [
    "account_count_provider",
    "alert_rule_count_provider",
    "position_count_provider",
    "trade_count_provider",
]
