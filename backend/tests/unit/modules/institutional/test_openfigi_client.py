"""Unit tests for ``app.modules.institutional.openfigi_client``.

Phase 3 / UNI-F13-003. We stub HTTP at the ``httpx`` layer via
``httpx.MockTransport`` — same pattern as the EDGAR client tests so the
two suites stay consistent.

Time-sensitive tests (rate limiter) monkey-patch ``asyncio.sleep`` to
keep the suite under a second.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from app.modules.institutional.openfigi_client import (
    FigiMapping,
    OpenFigiClient,
    OpenFigiRateLimiter,
)

# ───────────────────────── fixtures / helpers ─────────────────────────


async def _no_sleep(_seconds: float) -> None:
    return None


def _figi_row(
    ticker: str,
    name: str = "X CO",
    exch: str = "US",
    sec_type: str = "Common Stock",
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "exchCode": exch,
        "securityType": sec_type,
        "compositeFIGI": "BBG000000001",
    }


def _make_client(handler, api_key: str | None = None) -> OpenFigiClient:
    """Build an OpenFigiClient whose live httpx client is backed by ``handler``.

    The client's ``__aenter__`` opens a real httpx.AsyncClient; we close it
    and swap in our MockTransport-backed one, preserving the auth header.
    """
    return OpenFigiClient(api_key=api_key)


async def _open(client: OpenFigiClient, handler) -> None:
    """Enter the client + swap transport. Returns nothing — caller awaits exit."""
    await client.__aenter__()
    assert client._client is not None
    await client._client.aclose()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if client._api_key:
        headers["X-OPENFIGI-APIKEY"] = client._api_key
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=headers,
        timeout=client._timeout,
    )


# ───────────────────────── tests ─────────────────────────


async def test_map_cusips_returns_mapping() -> None:
    """Single CUSIP → one FigiMapping with ticker populated."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = [{"data": [_figi_row("AAPL", name="APPLE INC")]}]
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    await _open(client, handler)
    try:
        out = await client.map_cusips(["037833100"])
    finally:
        await client.__aexit__()

    assert len(out) == 1
    assert isinstance(out[0], FigiMapping)
    assert out[0].cusip == "037833100"
    assert out[0].ticker == "AAPL"
    assert out[0].exch_code == "US"
    assert out[0].security_type == "Common Stock"
    assert out[0].error is None


async def test_map_cusips_batches_above_10_free_tier() -> None:
    """Free tier chunks at 10 mappings per HTTP call."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append(len(body))
        # Return one stub row per request body item.
        resp = [{"data": [_figi_row(f"T{i}")]} for i in range(len(body))]
        return httpx.Response(200, json=resp)

    client = _make_client(handler, api_key=None)
    await _open(client, handler)
    try:
        # 25 CUSIPs → 3 chunks (10 + 10 + 5).
        cusips = [f"{i:09d}" for i in range(25)]
        out = await client.map_cusips(cusips)
    finally:
        await client.__aexit__()

    assert calls == [10, 10, 5]
    assert len(out) == 25
    assert all(m.ticker is not None for m in out)


async def test_map_cusips_handles_errors_per_row() -> None:
    """Per-row error field → ticker None, error populated."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = [
            {"data": [_figi_row("AAPL")]},
            {"error": "No identifier found."},
            {"data": []},  # empty data array, no error
        ]
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    await _open(client, handler)
    try:
        out = await client.map_cusips(["037833100", "999999999", "ZZZZZZZZZ"])
    finally:
        await client.__aexit__()

    assert out[0].ticker == "AAPL"
    assert out[1].ticker is None
    assert out[1].error == "No identifier found."
    assert out[2].ticker is None
    assert out[2].error == "no_us_common_stock"


async def test_rate_limiter_25_per_min_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bucket exhausted within the window → ``acquire`` waits until reset."""
    # Make refill instantaneous by fast-forwarding ``time.monotonic``.
    monkeypatch.setattr(
        "app.modules.institutional.openfigi_client.asyncio.sleep",
        _no_sleep,
    )

    limiter = OpenFigiRateLimiter(max_per_min=3)
    # Drain the bucket.
    for _ in range(3):
        await limiter.acquire()

    # Force the limiter into a "must wait" path. We override _reset_at to be
    # very near now → after _no_sleep the second pass through the loop will
    # see now >= reset_at and refill.
    limiter._reset_at = time.monotonic() + 0.001

    # This call should not hang the test (sleep is patched out).
    await limiter.acquire()
    # The bucket refilled to max, then we consumed one.
    assert limiter._tokens == limiter._max - 1


async def test_rate_limiter_auth_250_per_min() -> None:
    """Authed limiter exposes 250 token budget at construction."""
    limiter = OpenFigiRateLimiter(max_per_min=250)
    assert limiter._tokens == 250
    assert limiter._max == 250


async def test_map_cusips_filters_non_us() -> None:
    """Non-US exchCode rows must NOT produce a ticker."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = [
            {"data": [_figi_row("XYZ", exch="LN", sec_type="Common Stock")]},
        ]
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    await _open(client, handler)
    try:
        out = await client.map_cusips(["123456789"])
    finally:
        await client.__aexit__()

    assert out[0].ticker is None
    assert out[0].error == "no_us_common_stock"


async def test_map_cusips_filters_non_common_stock() -> None:
    """Preferred / ADR / fund unit must be rejected even when US-listed."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = [
            # Preferred shares — must be rejected.
            {"data": [_figi_row("PFD", exch="US", sec_type="Preferred Stock")]},
            # Real common stock — must pass.
            {"data": [_figi_row("NVDA", exch="US", sec_type="Common Stock")]},
        ]
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    await _open(client, handler)
    try:
        out = await client.map_cusips(["AAA111111", "BBB222222"])
    finally:
        await client.__aexit__()

    assert out[0].ticker is None
    assert out[1].ticker == "NVDA"


async def test_map_cusips_empty_list_returns_empty() -> None:
    client = _make_client(lambda r: httpx.Response(500))
    await _open(client, lambda r: httpx.Response(500))
    try:
        out = await client.map_cusips([])
    finally:
        await client.__aexit__()
    assert out == []


async def test_map_cusips_skips_empty_cusips_locally() -> None:
    """Empty / whitespace inputs short-circuit — no HTTP cost, slot preserved."""
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seen.append(len(body))
        # Echo only the live (non-empty) CUSIPs.
        return httpx.Response(
            200,
            json=[{"data": [_figi_row(f"T{i}")]} for i in range(len(body))],
        )

    client = _make_client(handler)
    await _open(client, handler)
    try:
        out = await client.map_cusips(["037833100", "", "  ", "594918104"])
    finally:
        await client.__aexit__()

    # Only 2 CUSIPs were sent over the wire.
    assert seen == [2]
    assert out[0].ticker == "T0"
    assert out[1].ticker is None  # empty
    assert out[1].error == "empty_cusip"
    assert out[2].ticker is None  # whitespace
    assert out[3].ticker == "T1"
