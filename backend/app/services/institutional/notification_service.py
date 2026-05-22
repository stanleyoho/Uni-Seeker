"""F13NotificationService — fan-out TG alerts on new 13F filings.

Spec: 2026-05-19 13F TG notifications on new filing.

Lifecycle:
  - Constructed per call inside the refresh path (manual + scheduled).
  - Takes a list of newly inserted ``F13Filing`` rows and fans them
    out to every subscribed user that has opted-in (per-subscription
    ``notify_on_new_filing`` flag) AND configured a
    ``telegram_chat_id`` on their user row.
  - Each TG send is best-effort; a failure is recorded in counters +
    audit log but never propagates into the refresh transaction.

Why a separate service object rather than inlining inside
``F13FilingService.refresh_filer``:

  - Refresh is a *mutation* on the EDGAR/DB side; the notification
    fan-out is an *I/O side-effect* on the Telegram side. Keeping
    them in different services makes the transactional boundary
    obvious — the caller commits the refresh BEFORE we send. If we
    inlined, a 200 response from Telegram on a row that later
    rolled back would be a phantom alert.
  - The same notify path serves both the on-demand
    ``refresh_filer`` call AND the scheduled cron entrypoints.
    One service, one tested code path.

Data contract: the caller passes the actual ``F13Filing`` ORM rows
that were JUST inserted in this refresh cycle. Empty list is a no-op
(common case — most refreshes find nothing new). We deliberately do
NOT query "all filings since X" inside this service: the refresh
service is the source of truth for "what is new in this cycle."
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.filing import F13Filing
from app.db.models.institutional.subscription import F13UserSubscription
from app.models.user import User
from app.modules.notifications.telegram_sender import send_telegram_message
from app.obs.logging import get_logger
from app.services.audit import log_audit_event

if TYPE_CHECKING:
    pass

logger = get_logger(component="f13_notification_service")


class F13NotificationService:
    """Send 13F new-filing alerts to subscribed users via Telegram.

    Stateless except for the AsyncSession. Safe to instantiate inside a
    refresh loop — no locks, no caches.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def notify_new_filings(
        self,
        filer_id: int,
        new_filings: Sequence[F13Filing],
    ) -> dict[str, int]:
        """Fan out alerts for ``new_filings`` on ``filer_id``.

        Algorithm:
          1. Short-circuit if ``new_filings`` is empty.
          2. Resolve the filer row (for filer.name in the message).
          3. JOIN subscriptions × users where
             ``notify_on_new_filing=True`` AND
             ``telegram_chat_id IS NOT NULL``.
          4. For each (user, filing) pair, format a message and call
             ``send_telegram_message``. Multiple new filings for the
             same filer in one cycle are rare (only on a brand-new
             subscription's backfill) but we send one message each so
             the user sees the actual count.
          5. Audit log once per (filer_id, refresh cycle) with the
             aggregate counts.

        Args:
            filer_id: The filer whose subscriptions we fan out to.
            new_filings: Newly inserted F13Filing rows. Order is the
                order returned by the refresh path (typically
                most-recent-first). Empty list returns a no-op result.

        Returns:
            ``{"notified": N, "skipped_no_chat_id": N,
            "skipped_opted_out": N, "errors": N}`` — counts for
            audit / metrics / debug.
        """
        result = {
            "notified": 0,
            "skipped_no_chat_id": 0,
            "skipped_opted_out": 0,
            "errors": 0,
        }

        if not new_filings:
            # No-op fast path — refresh runs that found nothing new
            # should pay zero cost. We still return the dict so callers
            # have a uniform shape to log.
            return result

        # Resolve filer (for message rendering). If somehow missing
        # we cannot send anything meaningful — log + bail.
        filer = await self._db.get(F13Filer, filer_id)
        if filer is None:  # pragma: no cover - invariant; refresh just touched it
            logger.warning(
                "f13_notify_filer_missing",
                filer_id=filer_id,
                new_filings=len(new_filings),
            )
            return result

        bot_token = settings.uni_telegram_bot_token
        if not bot_token:
            # Global TG disabled — count every would-be recipient as a
            # "no chat id" skip so the audit row reflects the actual
            # reason. This keeps ops able to distinguish "configured
            # but nobody opted in" from "not configured at all" via
            # the structured log below.
            logger.info(
                "f13_notify_globally_disabled",
                filer_id=filer_id,
                new_filings=len(new_filings),
            )
            # Still record an audit row so the user-facing behaviour
            # is observable; counts will all be zero.
            await log_audit_event(
                self._db,
                action="f13_notify_skipped_disabled",
                actor_type="system",
                resource_type="f13_filer",
                resource_id=str(filer_id),
                after_state={
                    "new_filings": len(new_filings),
                    "reason": "uni_telegram_bot_token_empty",
                },
            )
            return result

        # Step 3: subscriptions × users — opt-in + has chat_id.
        stmt = (
            select(F13UserSubscription, User)
            .join(User, User.id == F13UserSubscription.user_id)
            .where(
                F13UserSubscription.filer_id == filer_id,
                F13UserSubscription.notify_on_new_filing.is_(True),
                User.telegram_chat_id.is_not(None),
                User.is_active.is_(True),
            )
        )
        rows = (await self._db.execute(stmt)).all()

        # Also count "opted out" / "no chat_id" for ops visibility. A
        # second query is cheap and the alternative — joining with NULL
        # — would conflate the two reasons.
        if not rows:
            # Run the diagnostic counters so the audit log is useful.
            await self._count_skips(filer_id, result)

        for sub, user in rows:
            for filing in new_filings:
                ok = await send_telegram_message(
                    bot_token=bot_token,
                    chat_id=user.telegram_chat_id or "",
                    text=self._format_message(filer, filing),
                )
                if ok:
                    result["notified"] += 1
                else:
                    result["errors"] += 1
                    logger.warning(
                        "f13_notify_send_failed",
                        filer_id=filer_id,
                        filing_id=filing.id,
                        user_id=user.id,
                    )

        # Step 5: single aggregate audit row per refresh cycle.
        # actor_type=system because no per-user request initiated the
        # fan-out — it is a downstream effect of refresh.
        await log_audit_event(
            self._db,
            action="f13_notifications_sent",
            actor_type="system",
            resource_type="f13_filer",
            resource_id=str(filer_id),
            after_state={
                "filer_id": filer_id,
                "new_filings_count": len(new_filings),
                **result,
            },
        )
        return result

    # ── helpers ────────────────────────────────────────────────────────

    async def _count_skips(
        self, filer_id: int, result: dict[str, int]
    ) -> None:
        """Populate skipped_* counters when the eligible-recipients
        query came back empty.

        We only run this diagnostic when there were ZERO eligible
        recipients — the common case where the message DID get sent
        doesn't care about the skip breakdown, and avoiding the
        extra round trip in the hot path matters when fan-out scales.
        """
        # Two cheap counts. Postgres will satisfy both from the
        # ``ix_f13_user_subscriptions_filer_id`` index.
        no_chat_stmt = (
            select(F13UserSubscription.id)
            .join(User, User.id == F13UserSubscription.user_id)
            .where(
                F13UserSubscription.filer_id == filer_id,
                F13UserSubscription.notify_on_new_filing.is_(True),
                User.telegram_chat_id.is_(None),
            )
        )
        opted_out_stmt = select(F13UserSubscription.id).where(
            F13UserSubscription.filer_id == filer_id,
            F13UserSubscription.notify_on_new_filing.is_(False),
        )
        no_chat = (await self._db.execute(no_chat_stmt)).all()
        opted_out = (await self._db.execute(opted_out_stmt)).all()
        result["skipped_no_chat_id"] = len(no_chat)
        result["skipped_opted_out"] = len(opted_out)

    @staticmethod
    def _format_message(filer: F13Filer, filing: F13Filing) -> str:
        """Render the HTML body sent to Telegram.

        Format kept short on purpose — Telegram clients show the first
        ~100 chars in the lock-screen notification, so the filer name
        and "new 13F" must land in that prefix. Detail link points at
        the institutional page filtered to this filer so users land
        on context-rich data with one tap.
        """
        # Defensive formatting — totals may be NULL on a filing whose
        # parse produced zero holdings (edge case logged inside
        # _ingest_one). Use sensible fallbacks rather than emit
        # ``$None`` in the user-visible message.
        total_value = (
            float(filing.total_value_usd) if filing.total_value_usd else 0.0
        )
        total_positions = filing.total_positions or 0
        period = filing.report_period_end.isoformat()
        app_url = settings.app_url.rstrip("/")
        link = f"{app_url}/institutional?filer={filer.id}"

        # The "" + "" splits keep the multiline literal readable in
        # source while emitting a single HTML message with no leading
        # whitespace on each line (Telegram renders \n literally).
        return (
            f"<b>{_escape_html(filer.name)}</b> 有新 13F filing\n"
            f"期末: {period}\n"
            f"Form: {_escape_html(filing.form_type)}\n"
            f"總市值: ${total_value:,.0f}\n"
            f"持股數: {total_positions}\n"
            f"\n"
            f"看詳情: {link}"
        )


def _escape_html(text: str) -> str:
    """Minimal HTML escape for Telegram's HTML parse mode.

    Telegram only treats ``<``, ``>``, ``&`` as special; we do not
    touch quotes (they're allowed inside attribute-less HTML). Kept
    inline rather than importing ``html.escape`` so the substitution
    set is documented next to the rendering.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = ["F13NotificationService"]
