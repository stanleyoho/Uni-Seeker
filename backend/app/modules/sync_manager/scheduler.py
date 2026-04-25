"""Central scheduler that orchestrates all sync tasks."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sync_state import SyncState
from app.modules.notifier.telegram import TelegramNotifier
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask
from app.modules.sync_manager.tasks.margin import MarginSyncTask
from app.modules.sync_manager.tasks.per_pbr import PerPbrSyncTask
from app.modules.sync_manager.tasks.prices import PriceSyncTask
from app.modules.sync_manager.tasks.stock_info import StockInfoSyncTask

logger = structlog.get_logger()

# Execution order: stock_info first (so stocks table is up to date),
# then the per-stock datasets.
_TASK_ORDER: list[str] = ["stock_info", "prices", "margin", "per_pbr"]


class SyncScheduler:
    """Manages rate-limited execution of sync tasks."""

    def __init__(self, max_requests: int = 550) -> None:
        self._rate_limiter = RateLimiter(max_requests=max_requests)
        self._tasks: dict[str, SyncTask] = {
            "stock_info": StockInfoSyncTask(),
            "prices": PriceSyncTask(),
            "margin": MarginSyncTask(),
            "per_pbr": PerPbrSyncTask(),
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

        # Mark running
        await self._set_global_status(db, task_name, "running")

        try:
            result = await task.run(db, self._rate_limiter, batch_size)
        except Exception as exc:
            logger.error("sync_task_exception", task=task_name, error=str(exc))
            await self._set_global_status(
                db, task_name, "error", error_message=str(exc)[:500]
            )
            return SyncResult(
                dataset=task_name,
                stopped_reason="error",
                errors=1,
                error_details=[str(exc)],
            )

        # Final status based on result
        final_status = (
            "completed" if result.stopped_reason == "completed" else "error"
        )
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
                    "sync_run_all_rate_limit_stop",
                    stopped_at=name,
                    remaining=self._rate_limiter.remaining,
                )
                break

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

    async def get_status(self, db: AsyncSession) -> list[dict]:
        """Return the current sync state for every dataset."""
        q = await db.execute(
            select(SyncState).where(SyncState.stock_id.is_(None))
        )
        states = q.scalars().all()

        rows: list[dict] = []
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
                    "last_run_at": (
                        s.last_run_at.isoformat() if s and s.last_run_at else None
                    ),
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
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        now = datetime.now(timezone.utc)
        stmt = pg_insert(SyncState).values(
            dataset=dataset,
            stock_id=None,
            status=status,
            last_run_at=now,
            error_message=error_message,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_sync_state",
            set_={
                "status": status,
                "last_run_at": now,
                "error_message": error_message,
            },
        )
        await db.execute(stmt)
        await db.commit()
