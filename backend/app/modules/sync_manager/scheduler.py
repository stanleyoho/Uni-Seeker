"""Central scheduler that orchestrates all sync tasks."""

from __future__ import annotations

import traceback
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sync_state import SyncState
from app.modules.notifier.telegram import TelegramNotifier
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask
from app.modules.sync_manager.tasks.f13_filings import F13FilingsSyncTask
from app.modules.sync_manager.tasks.financials import FinancialsSyncTask
from app.modules.sync_manager.tasks.industry import IndustryAggregatesSyncTask
from app.modules.sync_manager.tasks.margin import MarginSyncTask
from app.modules.sync_manager.tasks.per_pbr import PerPbrSyncTask
from app.modules.sync_manager.tasks.prices import PriceSyncTask
from app.modules.sync_manager.tasks.revenue import RevenueSyncTask
from app.modules.sync_manager.tasks.stock_info import StockInfoSyncTask
from app.modules.sync_manager.tasks.tw_institutional import TwInstitutionalSyncTask
from app.modules.sync_manager.tasks.valuation import ValuationSyncTask
from app.obs.metrics import SYNC_TASK_FAILURES_TOTAL

# error_message column on sync_states is String(2000) since UNI_SYNC_002.
# Truncate to that ceiling rather than risk a `value too long` write failure
# (which would itself become a silent fail).
_ERROR_MESSAGE_MAX_LEN = 2000

logger = structlog.get_logger()

# Execution order: stock_info first (so stocks table is up to date),
# then the per-stock datasets, and finally industry-level aggregates.
# ``f13_filings`` runs last because it talks to SEC EDGAR (not FinMind)
# and therefore consumes a *separate* rate budget — placing it at the
# tail guarantees the upstream FinMind rate exhaustion does not deprive
# 13F refreshes of their independent EDGAR allotment.
_TASK_ORDER: list[str] = [
    "stock_info",
    "prices",
    "margin",
    # tw_institutional (三大法人) — TWSE publishes ~17:00 Taipei. Placed
    # right after margin so chip-data signals see a consistent trading
    # day. Same per-stock FinMind cost profile as margin; placement keeps
    # rate-budget pressure at the front of the chain so industry_aggregates
    # and f13_filings still receive tail headroom.
    "tw_institutional",
    "per_pbr",
    "revenue",
    "financials",
    "valuation",
    "industry_aggregates",
    "f13_filings",
]


class SyncScheduler:
    """Manages rate-limited execution of sync tasks."""

    def __init__(self, max_requests: int = 550) -> None:
        self._rate_limiter = RateLimiter(max_requests=max_requests)
        self._tasks: dict[str, SyncTask] = {
            "stock_info": StockInfoSyncTask(),
            "prices": PriceSyncTask(),
            "margin": MarginSyncTask(),
            "tw_institutional": TwInstitutionalSyncTask(),
            "per_pbr": PerPbrSyncTask(),
            "revenue": RevenueSyncTask(),
            "financials": FinancialsSyncTask(),
            "valuation": ValuationSyncTask(),
            "industry_aggregates": IndustryAggregatesSyncTask(),
            "f13_filings": F13FilingsSyncTask(),
        }
        self._notifier: TelegramNotifier | None = None

        if settings.telegram_bot_token and settings.telegram_chat_id:
            self._notifier = TelegramNotifier(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )

    @property
    def task_names(self) -> list[str]:
        return list(self._tasks.keys())

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run_task(
        self,
        task_name: str,
        db: AsyncSession,
        batch_size: int = 50,
    ) -> SyncResult:
        """Execute a single named task.

        Raises ``KeyError`` if *task_name* is not registered.
        """
        task = self._tasks[task_name]

        # Tag the Sentry scope so any exception captured during this run is
        # searchable by task/dataset (fail-soft when Sentry isn't initialised).
        from app.obs.sentry import set_task_tags

        set_task_tags(task=task_name, dataset=task_name)

        # Mark running
        await self._set_global_status(db, task_name, "running")

        try:
            result = await task.run(db, self._rate_limiter, batch_size)
        except Exception as exc:
            # 2026-04-30 silent-fail incident hardening:
            # Any exception MUST (a) write a non-empty error_message so an
            # operator audit can distinguish "ran clean with 0 rows" from
            # "crashed with no trace", and (b) increment a Prometheus counter
            # so the failure is visible without DB inspection. status="failed"
            # is reserved for the exception path; "error" was reused by the
            # rate_limit-vs-error branch below and conflated the two cases.
            error_type = type(exc).__name__
            # Prepend "{ExceptionClass}: {message}\n" so the class name + reason
            # survive truncation. Plain `traceback.format_exc()` puts the class
            # line at the END of the traceback; with a 500-char cap on
            # sync_states.error_message that final line is the first thing to
            # be cut, hiding exactly the info operators need most.
            tb_text = f"{error_type}: {exc}\n{traceback.format_exc()}"
            logger.error(
                "sync_task_exception",
                task=task_name,
                error_type=error_type,
                error=str(exc),
            )
            SYNC_TASK_FAILURES_TOTAL.labels(task=task_name, error_type=error_type).inc()
            try:
                await self._set_global_status(
                    db,
                    task_name,
                    "failed",
                    error_message=tb_text[:_ERROR_MESSAGE_MAX_LEN],
                )
            except Exception as status_exc:
                # The status write itself failed (the exact 4/30 mechanism:
                # missing partial unique index → InFailedSQLTransactionError).
                # Log loudly; counter already incremented above so observability
                # is preserved even if DB is uncooperative. Do not swallow.
                logger.error(
                    "sync_task_status_write_failed",
                    task=task_name,
                    original_error_type=error_type,
                    status_write_error=str(status_exc),
                )
            return SyncResult(
                dataset=task_name,
                stopped_reason="error",
                errors=1,
                error_details=[f"{error_type}: {exc}"],
            )

        # Final status based on result
        if result.stopped_reason == "completed":
            final_status = "completed"
        elif result.stopped_reason == "rate_limit":
            final_status = "partial"
        else:
            final_status = "error"
        await self._set_global_status(db, task_name, final_status)
        return result

    async def run_all(
        self,
        db: AsyncSession,
        batch_size: int = 50,
    ) -> list[SyncResult]:
        """Execute every task in the canonical order.

        Stops early if the rate limiter is exhausted.
        """
        results: list[SyncResult] = []
        for name in _TASK_ORDER:
            logger.info("sync_run_all_start_task", task=name)
            result = await self.run_task(name, db, batch_size)
            results.append(result)

            if result.stopped_reason == "rate_limit":
                logger.warning(
                    "sync_run_all_task_rate_limited",
                    task=name,
                    remaining=self._rate_limiter.remaining,
                )
                # Continue to next task - other datasets may need fewer API calls

        return results

    async def run_all_with_notify(
        self,
        db: AsyncSession,
        batch_size: int = 50,
    ) -> list[SyncResult]:
        """Execute every task in order and send Telegram notifications."""
        await self._notify("\U0001f504 <b>Uni-Seeker 資料同步開始</b>")

        results = await self.run_all(db, batch_size)

        msg = self._format_results(results)
        await self._notify(msg)

        return results

    # ------------------------------------------------------------------
    # Telegram helpers
    # ------------------------------------------------------------------

    async def _notify(self, message: str) -> None:
        """Send a Telegram notification if configured. Auto-prefixes [Uni-Seeker]."""
        if self._notifier:
            try:
                prefixed = f"[Uni-Seeker]\n{message}"
                await self._notifier.send(prefixed)
            except Exception as e:
                logger.error("telegram_notify_failed", error=str(e))

    def _format_results(self, results: list[SyncResult]) -> str:
        """Format sync results as an HTML message for Telegram."""
        lines: list[str] = ["\U0001f4ca <b>Uni-Seeker 同步完成</b>\n"]
        total_records = 0
        total_errors = 0

        for r in results:
            if r.stopped_reason == "completed":
                icon = "\u2705"
            elif r.stopped_reason == "rate_limit":
                icon = "\u26a0\ufe0f"
            else:
                icon = "\u274c"
            lines.append(
                f"{icon} <b>{r.dataset}</b>: {r.records_synced} 筆 ({r.stocks_processed} 支)"
            )
            # Surface per-task breakdown (e.g. stock_info: 新增 N · 改名 M · 換產業 K).
            if r.details:
                non_zero = [(k, v) for k, v in r.details.items() if v]
                if non_zero:
                    body = " · ".join(f"{k} {v}" for k, v in non_zero)
                    lines.append(f"   \u2514 {body}")
            for label, examples in r.extras.items():
                if examples:
                    lines.append(f"   \u2514 {label}: {', '.join(examples)}")
            if r.errors > 0:
                lines.append(f"   \u2514 {r.errors} 錯誤")
            total_records += r.records_synced
            total_errors += r.errors

        lines.append(f"\n\U0001f4c8 合計: {total_records} 筆資料")
        if total_errors > 0:
            lines.append(f"\u26a0\ufe0f {total_errors} 個錯誤")

        lines.append(
            f"\U0001f50b 剩餘額度: {self._rate_limiter.remaining}/{self._rate_limiter._max}"
        )

        return "\n".join(lines)

    async def get_status(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Return the current sync state for every dataset."""
        q = await db.execute(select(SyncState).where(SyncState.stock_id.is_(None)))
        states = q.scalars().all()

        rows: list[dict[str, Any]] = []
        state_map = {s.dataset: s for s in states}
        for name in _TASK_ORDER:
            s = state_map.get(name)
            rows.append(
                {
                    "dataset": name,
                    "status": s.status if s else "never_run",
                    "last_synced_date": (
                        s.last_synced_date.isoformat() if s and s.last_synced_date else None
                    ),
                    "last_run_at": (s.last_run_at.isoformat() if s and s.last_run_at else None),
                    "records_synced": s.records_synced if s else 0,
                    "error_message": s.error_message if s else None,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _set_global_status(
        self,
        db: AsyncSession,
        dataset: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Update (or create) the global sync-state row for a dataset."""
        now = datetime.now(UTC)
        # Use partial unique index uq_sync_state_global (dataset WHERE stock_id IS NULL)
        existing = await db.execute(
            select(SyncState).where(
                SyncState.dataset == dataset,
                SyncState.stock_id.is_(None),
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.status = status
            row.last_run_at = now
            row.error_message = error_message
        else:
            db.add(
                SyncState(
                    dataset=dataset,
                    stock_id=None,
                    status=status,
                    last_run_at=now,
                    error_message=error_message,
                )
            )
        await db.commit()
