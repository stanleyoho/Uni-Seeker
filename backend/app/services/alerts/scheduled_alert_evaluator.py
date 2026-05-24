"""Scheduled alert evaluator — fan out user-defined rule evaluation.

Cadence per tier (UNI-ALERT-001):

  PRO    — every 1h on the hour
  BASIC  — every 6h on the hour (00:00 / 06:00 / 12:00 / 18:00 UTC)
  FREE   — NOT scheduled (max_alert_rules=0 → no rules possible)

Why per-tier cadence rather than one fast cron?
- Pro pays for snappier alerts.
- Every cron tick pays a yfinance request budget per user; the slower
  basic cron keeps the burn rate down on the lowest-margin paid tier.

Anti-coupling contract:
- The ``*_entrypoint`` callables are zero-arg APScheduler hooks. They
  open their own session and ``LivePriceFetcher``.
- ``evaluate_for_tier`` takes both as parameters so unit tests can
  inject ``MockLivePriceFetcher`` against the shared db fixture.
- Exceptions raised by ``AlertService.evaluate_user_rules`` are
  caught per-user — one user's bad rule cannot abort the whole tier
  run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.models.enums import UserTier
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.portfolio.live_price_fetcher import LivePriceFetcher


logger = structlog.get_logger(__name__)


async def evaluate_for_tier(
    db: AsyncSession,
    fetcher: LivePriceFetcher,
    tier: UserTier,
) -> dict[str, int]:
    """Evaluate every active rule across all users on ``tier``.

    Loops users one at a time on purpose — each user has their own
    rules, positions, and chat_id, so there is no batching win from
    pulling everyone at once. Per-user errors are isolated.

    Returns aggregate counters for ops logging.
    """
    from app.services.alerts.alert_service import AlertService

    counts = {
        "users_processed": 0,
        "users_with_rules": 0,
        "evaluated": 0,
        "triggered": 0,
        "notified": 0,
        "errors": 0,
    }

    result = await db.execute(select(User).where(User.tier == tier, User.is_active.is_(True)))
    users = list(result.scalars().all())

    for user in users:
        counts["users_processed"] += 1
        try:
            service = AlertService(db, user)
            user_counts = await service.evaluate_user_rules(fetcher)
        except Exception as exc:  # pragma: no cover - defensive
            counts["errors"] += 1
            logger.exception(
                "alert_eval_user_failed",
                user_id=user.id,
                error=str(exc),
            )
            continue

        if user_counts["evaluated"] > 0:
            counts["users_with_rules"] += 1
        counts["evaluated"] += user_counts["evaluated"]
        counts["triggered"] += user_counts["triggered"]
        counts["notified"] += user_counts["notified"]
        counts["errors"] += user_counts["errors"]

    return counts


# ── APScheduler entrypoints ────────────────────────────────────────────────


async def hourly_pro_alert_entrypoint() -> None:  # pragma: no cover - wiring
    """Pro tier 1h evaluation cycle."""
    from app.api.v1.holdings._deps import get_live_price_fetcher
    from app.database import async_session

    fetcher = get_live_price_fetcher()
    try:
        async with async_session() as db:
            try:
                result = await evaluate_for_tier(db, fetcher, UserTier.PRO)
                await db.commit()
                logger.info("alert_eval_pro_done", **result)
            except Exception:
                await db.rollback()
                raise
    except Exception:
        logger.exception("alert_eval_pro_entrypoint_failed")


async def six_hour_basic_alert_entrypoint() -> None:  # pragma: no cover - wiring
    """Basic tier 6h evaluation cycle."""
    from app.api.v1.holdings._deps import get_live_price_fetcher
    from app.database import async_session

    fetcher = get_live_price_fetcher()
    try:
        async with async_session() as db:
            try:
                result = await evaluate_for_tier(db, fetcher, UserTier.BASIC)
                await db.commit()
                logger.info("alert_eval_basic_done", **result)
            except Exception:
                await db.rollback()
                raise
    except Exception:
        logger.exception("alert_eval_basic_entrypoint_failed")


__all__ = [
    "evaluate_for_tier",
    "hourly_pro_alert_entrypoint",
    "six_hour_basic_alert_entrypoint",
]
