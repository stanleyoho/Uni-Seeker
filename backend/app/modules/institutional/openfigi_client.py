"""OpenFIGI API client for CUSIP → ticker resolution.

Phase 3 / UNI-F13-003 — proper CUSIP unmapped resolution. Layer 2 of the
4-layer strategy in :mod:`app.modules.institutional.cusip_mapper`. Y3
``NAME_LIKE`` fallback has low accuracy on issuer names that share tokens
(``CITIGROUP CORP`` collides with multiple Citigroup subsidiaries); the
authoritative path is CUSIP → ticker via OpenFIGI, then ticker →
``stocks.symbol`` lookup.

API summary (https://www.openfigi.com/api):
    - POST https://api.openfigi.com/v3/mapping
    - Body: list of {idType: "ID_CUSIP", idValue: "<cusip>"} (parallel array)
    - Header: ``X-OPENFIGI-APIKEY`` optional (free=25 req/min @ 10 mappings;
      authed=250 req/min @ 100 mappings)
    - Response: list of {data: [{ticker, name, exchCode, securityType, ...}],
      error?: str} same length as input

Rate-limit math:
    - No auth:   25 req/min × 10 mappings  =    250 mappings/min
    - Authed:   250 req/min × 100 mappings = 25 000 mappings/min, 60k/day

We collect EXACT-miss CUSIPs in the caller (``cusip_mapper``) and emit a
single batched call per chunk — this is dramatically cheaper than
per-CUSIP HTTP roundtrips.

Anti-coupling: NO imports from ``app.db.*``, ``fastapi``, or
``smart_money``. Same surface contract as :mod:`edgar_client`.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.obs.logging import get_logger

__all__ = [
    "FigiMapping",
    "OpenFigiClient",
    "OpenFigiRateLimiter",
    "OpenFigiTransientError",
]

logger = get_logger(component="openfigi_client")


# ───────────────────────── public dataclasses ─────────────────────────


@dataclass(frozen=True)
class FigiMapping:
    """One CUSIP → security identity row from OpenFIGI.

    ``ticker`` is ``None`` when OpenFIGI knows the CUSIP but has no
    US-listed common-stock candidate (e.g. delisted, non-US, fund unit),
    OR when the API surfaces a per-row ``error`` (e.g. "No identifier
    found"). The caller treats both as a layer-2 miss and falls through
    to NAME_LIKE.

    ``exch_code`` for US-listed equities is ``"US"`` (NYSE/NASDAQ/etc.
    are sub-tagged in ``ticker`` like ``"NVDA UN"`` for the FIGI
    composite — we keep the plain ticker).
    """

    cusip: str
    ticker: str | None
    name: str | None
    exch_code: str | None  # e.g. "US"
    security_type: str | None  # e.g. "Common Stock"
    error: str | None


# ───────────────────────── errors ─────────────────────────


class OpenFigiTransientError(RuntimeError):
    """Raised after retries exhausted on a transient OpenFIGI failure.

    Caller is expected to log + degrade to NAME_LIKE rather than abort the
    backfill batch — one bad chunk should not poison the whole run.
    """


# ───────────────────────── rate limiter ─────────────────────────


class OpenFigiRateLimiter:
    """Per-minute token bucket — OpenFIGI's published policy is rolling 60s.

    Implementation notes:
    - Refills *all* tokens at the start of each 60-second window (not
      drip-by-drip). This matches OpenFIGI's documented behaviour: bursts
      are allowed up to the per-minute cap, the window resets atomically.
    - ``asyncio.Lock`` guards the counter so concurrent callers from the
      same event loop cannot oversubscribe. Cross-process deployment is
      out of scope for Phase 3 (single backfill worker).
    - Distinct from :class:`EdgarRateLimiter` which is per-second — both
      buckets are independent and live in their respective clients.
    """

    def __init__(self, max_per_min: int = 25) -> None:
        if max_per_min <= 0:
            raise ValueError("max_per_min must be positive")
        self._max = max_per_min
        self._tokens = max_per_min
        self._reset_at = time.monotonic() + 60.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a token is available, then consume one.

        Worst-case wait under a saturated bucket is ~60s — acceptable for
        a back-office backfill (caller already runs async). Callers that
        cannot tolerate this should use a smaller chunk size, not bypass
        the limiter.
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                if now >= self._reset_at:
                    self._tokens = self._max
                    self._reset_at = now + 60.0
                if self._tokens > 0:
                    self._tokens -= 1
                    return
                wait_s = max(0.0, self._reset_at - now)
            # Release lock before sleeping so other coroutines can refill
            # when their own window rolls over.
            await asyncio.sleep(wait_s)


# ───────────────────────── client ─────────────────────────


class OpenFigiClient:
    """Async client for OpenFIGI /v3/mapping.

    Usage::

        async with OpenFigiClient(api_key=os.getenv("OPENFIGI_API_KEY")) as c:
            mappings = await c.map_cusips(["037833100", "594918104", ...])

    Auto-chunks the input list against the per-call mapping cap, and
    awaits the rate limiter once per HTTP call. Failure modes:

    - 429 (rate limited): retry up to 3 times with exponential backoff
      that respects the ``Retry-After`` header when present.
    - 5xx (server error): same retry policy, ``OpenFigiTransientError``
      on exhaustion.
    - Per-row ``error`` field (e.g. "No identifier found"): mapped to
      ``FigiMapping(ticker=None, error=<msg>)`` — *not* retried, the
      CUSIP is simply unknown.
    - Non-US / non-common-stock candidates: filtered out, treated as
      "no ticker" (caller falls through to NAME_LIKE).
    """

    BASE_URL = "https://api.openfigi.com/v3"
    MAX_MAPPINGS_PER_CALL_FREE = 10
    MAX_MAPPINGS_PER_CALL_AUTH = 100

    _MAX_RETRIES = 3
    _BACKOFF_BASE_SECONDS = 1.0

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        rate_limiter: OpenFigiRateLimiter | None = None,
    ) -> None:
        # ``api_key`` may legitimately be None → free tier. We never raise
        # at construction so service code can wire this universally.
        self._api_key = (api_key or "").strip() or None
        self._timeout = timeout_seconds
        if rate_limiter is not None:
            self._limiter = rate_limiter
        else:
            self._limiter = OpenFigiRateLimiter(
                max_per_min=250 if self._api_key else 25
            )
        self._batch_size = (
            self.MAX_MAPPINGS_PER_CALL_AUTH
            if self._api_key
            else self.MAX_MAPPINGS_PER_CALL_FREE
        )
        self._client: httpx.AsyncClient | None = None

    # ── context manager ──

    async def __aenter__(self) -> OpenFigiClient:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["X-OPENFIGI-APIKEY"] = self._api_key
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── public API ──

    @property
    def batch_size(self) -> int:
        """Max mappings the client will pack into a single POST."""
        return self._batch_size

    async def map_cusips(self, cusips: list[str]) -> list[FigiMapping]:
        """Resolve CUSIPs → tickers in chunks, preserving input order.

        Filters to **US-listed common stock** before returning:
        ``exchCode == "US"`` AND ``securityType`` containing ``"Common Stock"``
        / ``"Common"``. Anything else (ADRs, foreign listings, fund units,
        preferred shares) returns ``FigiMapping(ticker=None, ...)`` so the
        caller can drop through to NAME_LIKE.

        Empty/whitespace CUSIPs in the input are *not* sent to OpenFIGI —
        they yield a synthetic empty mapping locally (zero HTTP cost).

        Args:
            cusips: list of 9-char CUSIPs. Duplicates allowed (we don't
                de-duplicate; the caller chooses whether to bother).

        Returns:
            same-length list of :class:`FigiMapping`, in input order.
        """
        if not cusips:
            return []

        # Pre-build the result skeleton so empty/invalid inputs short-circuit
        # without affecting positions of valid CUSIPs in the output.
        results: list[FigiMapping | None] = [None] * len(cusips)
        live_positions: list[int] = []
        live_cusips: list[str] = []

        for i, raw in enumerate(cusips):
            c = (raw or "").strip()
            if not c:
                results[i] = FigiMapping(
                    cusip="", ticker=None, name=None,
                    exch_code=None, security_type=None,
                    error="empty_cusip",
                )
            else:
                live_positions.append(i)
                live_cusips.append(c)

        # Chunk live CUSIPs against the per-call cap. One HTTP call per chunk.
        for start in range(0, len(live_cusips), self._batch_size):
            chunk = live_cusips[start : start + self._batch_size]
            chunk_positions = live_positions[start : start + self._batch_size]
            chunk_results = await self._post_mapping_chunk(chunk)
            for pos, mapping in zip(chunk_positions, chunk_results):
                results[pos] = mapping

        # All positions must be filled by now.
        return [r if r is not None else _empty_mapping("") for r in results]

    # ── internals ──

    async def _post_mapping_chunk(
        self, cusips: list[str]
    ) -> list[FigiMapping]:
        """POST a single chunk (≤ ``batch_size``) and parse the response.

        OpenFIGI returns a parallel array: response[i] corresponds to
        request body[i]. Each element is either ``{"data": [...]}`` or
        ``{"error": "<msg>"}``. We pick the first US-listed common-stock
        candidate from ``data``; if none qualifies, we treat the row as
        a layer-2 miss.
        """
        body = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
        payload = await self._post_with_retry(f"{self.BASE_URL}/mapping", body)
        # Normalize to list at the same length as ``cusips`` — defensive in
        # case the API ever returns a shorter array on partial failure.
        if not isinstance(payload, list):
            logger.warning(
                "openfigi_unexpected_payload_shape",
                payload_type=type(payload).__name__,
                chunk_size=len(cusips),
            )
            return [_empty_mapping(c, error="bad_payload") for c in cusips]

        out: list[FigiMapping] = []
        for cusip, row in zip(cusips, payload):
            if not isinstance(row, dict):
                out.append(_empty_mapping(cusip, error="bad_row"))
                continue
            err = row.get("warning") or row.get("error")
            data = row.get("data") or []
            if err and not data:
                out.append(_empty_mapping(cusip, error=str(err)))
                continue
            picked = _pick_us_common_stock(data)
            if picked is None:
                out.append(_empty_mapping(cusip, error="no_us_common_stock"))
                continue
            out.append(
                FigiMapping(
                    cusip=cusip,
                    ticker=picked.get("ticker") or None,
                    name=picked.get("name") or None,
                    exch_code=picked.get("exchCode") or None,
                    security_type=picked.get("securityType") or None,
                    error=None,
                )
            )

        # If OpenFIGI ever returns a shorter list (defensive), pad misses.
        if len(out) < len(cusips):
            for cusip in cusips[len(out) :]:
                out.append(_empty_mapping(cusip, error="missing_row"))
        return out

    async def _post_with_retry(
        self, url: str, json_body: list[dict[str, str]]
    ) -> Any:
        if self._client is None:
            raise RuntimeError(
                "OpenFigiClient must be used as an async context manager "
                "(`async with OpenFigiClient(...) as c: ...`)"
            )

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.post(url, json=json_body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                wait_s = self._BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "openfigi_request_transport_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt >= self._MAX_RETRIES:
                    break
                await asyncio.sleep(wait_s)
                continue

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait_s = float(retry_after)
                    except ValueError:
                        wait_s = self._BACKOFF_BASE_SECONDS * (2 ** attempt)
                else:
                    wait_s = self._BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "openfigi_rate_limited",
                    url=url,
                    attempt=attempt + 1,
                    retry_after=retry_after,
                    wait_seconds=wait_s,
                )
                if attempt >= self._MAX_RETRIES:
                    last_exc = OpenFigiTransientError(
                        f"OpenFIGI rate-limited after {self._MAX_RETRIES + 1} attempts"
                    )
                    break
                await asyncio.sleep(wait_s)
                continue

            if 500 <= response.status_code < 600:
                wait_s = self._BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "openfigi_server_error",
                    url=url,
                    status=response.status_code,
                    attempt=attempt + 1,
                )
                last_exc = OpenFigiTransientError(
                    f"OpenFIGI returned {response.status_code} after retry"
                )
                if attempt >= self._MAX_RETRIES:
                    break
                await asyncio.sleep(wait_s)
                continue

            if 400 <= response.status_code < 500:
                # 4xx (other than 429) — caller mistake, do not retry.
                response.raise_for_status()

            return response.json()

        if isinstance(last_exc, OpenFigiTransientError):
            raise last_exc
        raise OpenFigiTransientError(
            f"OpenFIGI request failed after {self._MAX_RETRIES + 1} attempts: {last_exc!r}"
        )


# ───────────────────────── private helpers ─────────────────────────


def _empty_mapping(cusip: str, error: str | None = None) -> FigiMapping:
    return FigiMapping(
        cusip=cusip,
        ticker=None,
        name=None,
        exch_code=None,
        security_type=None,
        error=error,
    )


def _pick_us_common_stock(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most appropriate candidate from a FIGI ``data`` array.

    Preference order:
      1. ``exchCode == "US"`` AND ``securityType`` mentions "Common Stock"
         (the strict happy path — what we want 95% of the time).
      2. ``exchCode == "US"`` AND ``securityType`` simply contains
         "Common" (looser; covers e.g. "Common Shares").
      3. Otherwise: no pick, caller falls through.

    We *don't* fall back to non-US candidates here — the caller can decide
    whether NAME_LIKE on a domestic-only ``stocks`` table is more useful
    than a foreign FIGI ticker that won't match any Stock row anyway.
    """
    if not data:
        return None

    # Pass 1: strict.
    for row in data:
        if not isinstance(row, dict):
            continue
        if (row.get("exchCode") or "").upper() != "US":
            continue
        stype = (row.get("securityType") or "").lower()
        if "common stock" in stype:
            return row

    # Pass 2: loose Common.
    for row in data:
        if not isinstance(row, dict):
            continue
        if (row.get("exchCode") or "").upper() != "US":
            continue
        stype = (row.get("securityType") or "").lower()
        if "common" in stype:
            return row

    return None


def openfigi_api_key_from_env() -> str | None:
    """Convenience helper for CLI / job code.

    Reads ``OPENFIGI_API_KEY`` (raw OpenFIGI env name) first, then falls
    back to the app-prefixed ``UNI_OPENFIGI_API_KEY``. Returns None when
    both are missing — caller wires the client without auth (free tier).
    """
    return (
        os.getenv("OPENFIGI_API_KEY")
        or os.getenv("UNI_OPENFIGI_API_KEY")
        or None
    )
