"""Token-bucket rate limiter for FinMind API calls."""

from __future__ import annotations

import asyncio
import time
from collections import deque

import structlog

logger = structlog.get_logger()


class RateLimiter:
    """FinMind API rate limiter -- 600 calls/hour on the free tier.

    Reserves 50 calls for ad-hoc API usage, allowing up to *max_requests*
    calls within a sliding *window_seconds* window for batch sync jobs.
    """

    def __init__(
        self,
        max_requests: int = 550,
        window_seconds: int = 3600,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: deque[float] = deque()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def remaining(self) -> int:
        """Number of API calls still available in the current window."""
        self._purge_expired()
        return max(0, self._max - len(self._timestamps))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self) -> bool:
        """Try to consume one call permit.

        Returns ``True`` if the call was allowed, ``False`` if the limit
        has been reached.
        """
        self._purge_expired()
        if len(self._timestamps) >= self._max:
            logger.warning(
                "rate_limiter_exhausted",
                used=len(self._timestamps),
                max=self._max,
            )
            return False
        self._timestamps.append(time.monotonic())
        return True

    async def wait_and_acquire(self, timeout: float = 60.0) -> bool:
        """Block until a permit becomes available or *timeout* elapses.

        Returns ``True`` on success, ``False`` if the timeout expired
        before a permit could be obtained.
        """
        deadline = time.monotonic() + timeout
        while True:
            if await self.acquire():
                return True
            if time.monotonic() >= deadline:
                logger.warning("rate_limiter_timeout", timeout=timeout)
                return False
            # Sleep until the oldest timestamp expires (or 1 s, whichever
            # is shorter) so we don't spin-wait.
            if self._timestamps:
                wait = self._timestamps[0] + self._window - time.monotonic()
                wait = min(max(wait, 0.1), 1.0)
            else:
                wait = 0.1
            await asyncio.sleep(wait)

    def reset(self) -> None:
        """Clear all recorded timestamps (e.g. for testing)."""
        self._timestamps.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _purge_expired(self) -> None:
        """Remove timestamps that have fallen outside the sliding window."""
        cutoff = time.monotonic() - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
