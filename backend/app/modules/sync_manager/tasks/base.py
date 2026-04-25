"""Base class and result type for all sync tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sync_manager.rate_limiter import RateLimiter


@dataclass
class SyncResult:
    """Summary produced by a single sync-task run."""

    dataset: str
    stocks_processed: int = 0
    records_synced: int = 0
    errors: int = 0
    stopped_reason: str | None = None  # "completed", "rate_limit", "error"
    error_details: list[str] = field(default_factory=list)


class SyncTask(ABC):
    """Abstract base for a dataset synchronisation task."""

    dataset_name: str

    @abstractmethod
    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        """Execute the sync and return a summary result."""
        ...
