"""Unit tests for ``app.modules.institutional.edgar_client``.

Strategy: stub HTTP at the ``httpx`` layer via ``httpx.MockTransport``
(a first-party fake — no extra deps). Each test wires a fresh transport
that returns scripted responses; we then drive the client through its
public API and assert against captured requests.

Time-sensitive tests (rate limiter, backoff) monkey-patch
``asyncio.sleep`` so the suite finishes in <1s.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from app.modules.institutional.edgar_client import (
    EdgarClient,
    EdgarRateLimiter,
    EdgarTransientError,
)

# ───────────────────────── fixtures / helpers ─────────────────────────


def _submissions_payload(name: str = "Situational Awareness LP") -> dict[str, Any]:
    """Mimic the structure of ``data.sec.gov/submissions/CIK*.json``."""
    return {
        "cik": "2048840",
        "name": name,
        "filings": {
            "recent": {
                "form": ["13F-HR", "10-K", "13F-HR", "13F-HR/A", "13F-HR", "13F-HR"],
                "accessionNumber": [
                    "0001234567-25-000001",
                    "0009999999-25-000005",
                    "0001234567-24-000010",
                    "0001234567-24-000020",
                    "0001234567-24-000030",
                    "0001234567-23-000040",
                ],
                "primaryDocument": [
                    "primary_doc.xml",
                    "10k.htm",
                    "primary_doc.xml",
                    "primary_doc.xml",
                    "primary_doc.xml",
                    "primary_doc.xml",
                ],
                "periodOfReport": [
                    "2025-12-31",
                    "2025-06-30",
                    "2025-09-30",
                    "2025-06-30",
                    "2025-03-31",
                    "2024-12-31",
                ],
                "filingDate": [
                    "2026-02-14",
                    "2025-08-01",
                    "2025-11-14",
                    "2025-08-30",
                    "2025-05-14",
                    "2025-02-14",
                ],
            }
        },
    }


async def _no_sleep(_seconds: float) -> None:
    """Drop-in for asyncio.sleep used to fast-forward retry/backoff tests."""
    return None


def _filing_index_payload(
    accession_no_dashes: str,
    cik_int: str = "2048840",
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mimic SEC's per-accession ``Archives/.../index.json`` directory listing.

    Default items match the ARK shape (``infotable.xml`` + ``primary_doc.xml``).
    """
    if items is None:
        items = [
            {"name": "infotable.xml", "type": "text.gif", "size": "85773"},
            {"name": "primary_doc.xml", "type": "text.gif", "size": "2055"},
        ]
    return {
        "directory": {
            "name": f"/Archives/edgar/data/{cik_int}/{accession_no_dashes}",
            "item": items,
        }
    }


def _make_router_handler(
    submissions_payload: dict[str, Any] | None = None,
    index_items: dict[str, list[dict[str, Any]]] | None = None,
):
    """Build an httpx mock handler that routes by URL path.

    - ``data.sec.gov/submissions/CIK*.json``  → submissions payload
    - ``www.sec.gov/Archives/.../index.json`` → per-accession listing
    - anything else → 404

    ``index_items`` maps ``accession_no_dashes`` → custom item list.
    Missing keys fall back to the default ARK-shape items.
    """
    sub = submissions_payload or _submissions_payload()
    idx_map = index_items or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/submissions/CIK" in path:
            return httpx.Response(200, json=sub)
        if path.endswith("/index.json"):
            # Path = /Archives/edgar/data/<cik>/<accession>/index.json
            parts = path.strip("/").split("/")
            accession = parts[-2]
            items = idx_map.get(accession)
            return httpx.Response(
                200, json=_filing_index_payload(accession, items=items)
            )
        return httpx.Response(404, text=f"unhandled mock path: {path}")

    return handler


# ───────────────────────── tests ─────────────────────────


async def test_user_agent_header_set() -> None:
    """Every request must carry the contact-email User-Agent header."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_submissions_payload())

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        # Swap in the mock transport on the active AsyncClient.
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        await client.get_filer_metadata("0002048840")

    assert len(captured) == 1
    assert captured[0].headers["user-agent"] == "Uni-Seeker contact@example.com"


async def test_rate_limiter_enforces_10_per_sec() -> None:
    """Token bucket should release at most ``max_per_sec`` tokens / sec.

    We pick a low cap (2 per sec) so the test stays fast yet still verifies
    that the second batch waits a measurable amount.
    """
    limiter = EdgarRateLimiter(max_per_sec=2)
    start = time.monotonic()
    # Drain the initial bucket.
    await limiter.acquire()
    await limiter.acquire()
    # Third acquire must wait ~0.5s for the bucket to refill at 2/sec.
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4, f"expected >=0.4s wait, got {elapsed:.3f}s"


async def test_429_retries_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 responses must retry up to 3 times with backoff, then succeed."""
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"}, text="rate limited")
        return httpx.Response(200, json=_submissions_payload())

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        # Replace transport.
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        meta = await client.get_filer_metadata("0002048840")

    assert call_count["n"] == 3
    assert meta.name == "Situational Awareness LP"


async def test_search_filers_by_name_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    search_payload = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "ciks": ["0002048840"],
                        "display_names": ["SITUATIONAL AWARENESS LP (CIK 0002048840) (Filer)"],
                    }
                },
                {
                    "_source": {
                        "ciks": ["0001067983"],
                        "display_names": ["BERKSHIRE HATHAWAY INC (CIK 0001067983) (Filer)"],
                    }
                },
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "search-index" in str(request.url)
        return httpx.Response(200, json=search_payload)

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        results = await client.search_filers_by_name("situational awareness")

    assert len(results) == 2
    assert results[0].cik == "0002048840"
    assert "SITUATIONAL" in (results[0].legal_name or "")
    assert results[1].cik == "0001067983"


async def test_get_filer_metadata_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        # CIK must be zero-padded in URL.
        assert "CIK0002048840.json" in str(request.url)
        return httpx.Response(200, json=_submissions_payload("Leopold's Fund"))

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        # Pass a non-padded CIK to verify the client pads it.
        meta = await client.get_filer_metadata("2048840")

    assert meta.cik == "0002048840"
    assert meta.name == "Leopold's Fund"


async def test_list_filings_for_filer_max_count_4(monkeypatch: pytest.MonkeyPatch) -> None:
    """``max_count=4`` truncates to ~1 year of quarterly filings."""
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    transport = httpx.MockTransport(_make_router_handler())
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        filings = await client.list_filings_for_filer("2048840", max_count=4)

    assert len(filings) == 4
    # Sorted DESC by report_period_end.
    periods = [f.report_period_end for f in filings]
    assert periods == sorted(periods, reverse=True)
    # URLs point at /Archives/edgar/data/<int_cik>/<no-dash-accession>/<primary>
    assert "/Archives/edgar/data/2048840/" in (filings[0].raw_xml_url or "")
    assert "-" not in filings[0].accession_number  # dashes stripped


async def test_list_filings_filter_form_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-13F forms (10-K, etc.) must be excluded by default."""
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    transport = httpx.MockTransport(_make_router_handler())
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        # Default form_types should drop the 10-K row entirely.
        filings = await client.list_filings_for_filer("2048840", max_count=10)

    assert all(f.form_type in {"13F-HR", "13F-HR/A"} for f in filings)
    # Submissions payload has 5 13F-form rows (4 HR + 1 HR/A); none should be 10-K.
    assert len(filings) == 5


async def test_list_filings_resolves_infotable_xml_via_index_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``raw_xml_url`` must point at the real infotable XML — NOT the
    XSL-rendered HTML view at ``xslForm13F_X02/primary_doc.xml``.

    Verifies that ``list_filings_for_filer`` fetches the per-accession
    ``index.json`` and pulls the infotable filename out of the directory
    listing. Covers both naming conventions in the wild:

    - ``infotable.xml`` (ARK convention)
    - ``<digits>.xml`` (Berkshire convention, accession-derived)
    """
    monkeypatch.setattr(
        "app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep
    )

    # The first 4 13F accessions in the submissions fixture:
    # 0001234567-25-000001 (period 2025-12-31) → infotable.xml
    # 0001234567-24-000010 (period 2025-09-30) → 53405.xml (Berkshire-style)
    # 0001234567-24-000020 (period 2025-06-30, 13F-HR/A) → form13fInfoTable.xml
    # 0001234567-24-000030 (period 2025-03-31) → infotable.xml (default)
    index_items = {
        "000123456725000001": [
            {"name": "infotable.xml", "type": "text.gif"},
            {"name": "primary_doc.xml", "type": "text.gif"},
        ],
        "000123456724000010": [
            {"name": "53405.xml", "type": "text.gif"},
            {"name": "primary_doc.xml", "type": "text.gif"},
        ],
        "000123456724000020": [
            {"name": "form13fInfoTable.xml", "type": "text.gif"},
            {"name": "primary_doc.xml", "type": "text.gif"},
        ],
    }
    transport = httpx.MockTransport(
        _make_router_handler(index_items=index_items)
    )
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        filings = await client.list_filings_for_filer("2048840", max_count=4)

    # Build accession → URL map for stable assertions (output is sorted
    # DESC by period, which we don't want to lock down here).
    url_by_acc = {f.accession_number: f.raw_xml_url for f in filings}
    cover_by_acc = {f.accession_number: f.cover_xml_url for f in filings}

    # No URL must route through the XSL renderer.
    for url in url_by_acc.values():
        assert url is not None
        assert "xslForm13F_X02" not in url

    # Each filing's raw_xml_url resolves to the correct co-resident XML.
    assert url_by_acc["000123456725000001"].endswith("/infotable.xml")
    assert url_by_acc["000123456724000010"].endswith("/53405.xml")
    assert url_by_acc["000123456724000020"].endswith("/form13fInfoTable.xml")

    # Cover sheet URLs are always primary_doc.xml under the accession dir.
    for cover in cover_by_acc.values():
        assert cover is not None
        assert cover.endswith("/primary_doc.xml")
        assert "xslForm13F_X02" not in cover


async def test_list_filings_returns_none_when_infotable_not_in_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the index.json lists no parseable infotable XML, the filing
    must surface with ``raw_xml_url=None`` (the service layer will skip
    it). We must NOT silently fall back to ``primary_doc.xml``.
    """
    monkeypatch.setattr(
        "app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep
    )

    # All filings get a degenerate index with only cover + non-XML files.
    degenerate_items = [
        {"name": "primary_doc.xml", "type": "text.gif"},
        {"name": "Financial_Report.xlsx", "type": "text.gif"},
    ]
    accessions = [
        "000123456725000001",
        "000123456724000010",
        "000123456724000020",
        "000123456724000030",
        "000123456723000040",
    ]
    index_items = dict.fromkeys(accessions, degenerate_items)
    transport = httpx.MockTransport(
        _make_router_handler(index_items=index_items)
    )
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        filings = await client.list_filings_for_filer("2048840", max_count=4)

    assert len(filings) == 4
    for f in filings:
        assert f.raw_xml_url is None
        # Cover URL is still constructable from accession + cik alone.
        assert f.cover_xml_url is not None
        assert f.cover_xml_url.endswith("/primary_doc.xml")


async def test_fetch_filing_xml_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    body = "<?xml version='1.0'?><informationTable/>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"Content-Type": "text/xml"})

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        xml = await client.fetch_filing_xml(
            "https://www.sec.gov/Archives/edgar/data/2048840/000123456725000001/primary_doc.xml"
        )

    assert xml == body


async def test_503_exhausts_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persistent 503 should raise EdgarTransientError after 3 retries."""
    monkeypatch.setattr("app.modules.institutional.edgar_client.asyncio.sleep", _no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    transport = httpx.MockTransport(handler)
    client = EdgarClient(user_agent="Uni-Seeker contact@example.com")
    async with client:
        assert client._client is not None
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": "Uni-Seeker contact@example.com"},
            follow_redirects=True,
        )
        with pytest.raises(EdgarTransientError):
            await client.get_filer_metadata("0002048840")


async def test_user_agent_validation_rejects_missing_email() -> None:
    """SEC policy requires contact email; reject UA without ``@``."""
    with pytest.raises(ValueError, match="contact email"):
        EdgarClient(user_agent="Uni-Seeker")
