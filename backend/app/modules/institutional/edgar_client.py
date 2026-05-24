"""SEC EDGAR async client — the ONE I/O surface of the institutional domain.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§3 (data source), §6.1 (module breakdown), §7.3 (rate-limit strategy),
§11.R3 (rate-limit risk mitigation).

Design highlights:
- ``httpx.AsyncClient`` aligned with backend's existing async style.
- ``EdgarRateLimiter`` enforces SEC's 10 req/sec fair-use policy via a
  token bucket. **Global** (process-wide when injected once) — SEC's
  policy treats the IP, not the request type, as the rate-limit subject.
- Required ``User-Agent`` header per SEC policy; missing/wrong UA → 403.
- Retry on 429 / 5xx with exponential backoff (max 3 retries). Respects
  ``Retry-After`` header on 429.
- Pure dataclasses (``FilerMetadata``, ``FilingMetadata``) as the
  module's outbound surface — no ORM coupling.

Anti-coupling: NO imports from ``app.db.*``, ``fastapi``, ``smart_money``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
import structlog

__all__ = [
    "EdgarClient",
    "EdgarRateLimiter",
    "EdgarTransientError",
    "FilerMetadata",
    "FilingMetadata",
]

logger = structlog.get_logger(__name__)


# ───────────────────────── public dataclasses ─────────────────────────


@dataclass(frozen=True)
class FilerMetadata:
    """Minimal filer identity from SEC submissions endpoint.

    ``cik`` is always 10-digit zero-padded (the canonical SEC form).
    """

    cik: str
    name: str
    legal_name: str | None = None


@dataclass(frozen=True)
class FilingMetadata:
    """One 13F filing reference.

    ``accession_number`` is stored **without dashes** (the form SEC uses
    in archive URLs). The dashed form ``0001234567-25-012345`` can be
    reconstructed by callers if they need to render it.

    13F filings ship **two** XML documents per accession:
    - ``cover_xml_url`` → ``primary_doc.xml``: cover sheet with filer
      identity, period, amendment flag. **Has no `<infoTable>` rows.**
    - ``raw_xml_url`` → the actual ``<informationTable>`` XML (filename
      varies per filer — ``infotable.xml``, ``form13fInfoTable.xml``,
      or accession-derived like ``53405.xml``). Resolved by walking the
      filing's ``index.json`` directory listing.

    ``raw_xml_url`` is ``None`` when the index lookup fails (e.g. SEC
    returns an unexpected layout). Callers must skip such filings and
    log — there is no holdings data to ingest without it. The submissions
    API's ``primaryDocument`` field points at ``xslForm13F_X02/primary_doc.xml``
    (an XSL-rendered HTML view) which is unparseable as XML — never
    use that path.
    """

    accession_number: str
    form_type: str  # "13F-HR" | "13F-HR/A" | "13F-NT"
    report_period_end: date
    filed_at: datetime
    raw_xml_url: str | None
    cover_xml_url: str | None = None


# ───────────────────────── errors ─────────────────────────


class EdgarTransientError(RuntimeError):
    """Raised after all retries exhausted on a transient EDGAR failure.

    Service layer is expected to translate this into a user-facing 503
    or schedule a retry — never propagate the raw httpx error type.
    """


# ───────────────────────── rate limiter ─────────────────────────


class EdgarRateLimiter:
    """Token-bucket limiter for SEC's 10 req/sec fair-use policy.

    Implementation notes:
    - **Token bucket** (not a plain semaphore) because we want a sliding
      window: 10 reqs over any rolling 1-second window, not 10 reqs that
      release one-by-one as siblings finish. The semaphore approach
      stalls bursts even when total bandwidth is fine.
    - Capacity equals refill rate so the bucket never accumulates beyond
      its per-second budget — SEC policy is about peak rate, not volume.
    - ``asyncio.Lock`` guards the refill/decrement so we are
      cooperatively safe under a single event loop. Cross-loop or
      cross-process usage is out of scope for Phase 1 (one app instance).
    """

    def __init__(self, max_per_sec: int = 10) -> None:
        if max_per_sec <= 0:
            raise ValueError("max_per_sec must be positive")
        self._max_per_sec: float = float(max_per_sec)
        self._capacity: float = float(max_per_sec)
        self._tokens: float = float(max_per_sec)
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a token is available, then consume one.

        Worst-case wait under burst is ~1/max_per_sec seconds; well under
        the typical 100ms+ EDGAR round-trip, so net latency overhead is
        negligible when the API is healthy.
        """
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Compute deficit → minimum wait before next token.
                deficit = 1.0 - self._tokens
                wait_seconds = deficit / self._max_per_sec
            # Release the lock before sleeping so peers can refill too.
            await asyncio.sleep(wait_seconds)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._max_per_sec)
        self._last_refill = now


# ───────────────────────── client ─────────────────────────


class EdgarClient:
    """Async client for the subset of SEC EDGAR endpoints we need.

    Required by SEC fair-use policy:
    - Set ``User-Agent`` header containing a real contact email.
    - Respect 10 req/sec rate cap (enforced by ``EdgarRateLimiter``).

    Usage::

        async with EdgarClient(user_agent="Uni-Seeker stanly7768@gmail.com") as c:
            meta = await c.get_filer_metadata("0002048840")
            filings = await c.list_filings_for_filer(meta.cik, max_count=4)
            xml = await c.fetch_filing_xml(filings[0].raw_xml_url)
    """

    BASE_URL = "https://www.sec.gov"
    DATA_URL = "https://data.sec.gov"
    FULLTEXT_URL = "https://efts.sec.gov"

    _MAX_RETRIES = 3
    _BACKOFF_BASE_SECONDS = 1.0

    def __init__(
        self,
        user_agent: str = "Uni-Seeker stanly7768@gmail.com",
        timeout_seconds: float = 30.0,
        rate_limiter: EdgarRateLimiter | None = None,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            # SEC explicitly requires a contact email. Refuse to silently
            # send a broken UA — would just get 403'd at runtime.
            raise ValueError("user_agent must include a contact email per SEC policy")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._limiter = rate_limiter or EdgarRateLimiter()
        self._client: httpx.AsyncClient | None = None

    # ── context manager ──

    async def __aenter__(self) -> EdgarClient:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/xml, */*",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── public API ──

    async def search_filers_by_name(self, name_query: str, limit: int = 20) -> list[FilerMetadata]:
        """Search EDGAR full-text index for filers with 13F-HR history.

        Hits ``efts.sec.gov/LATEST/search-index`` and de-duplicates by
        (CIK, name). Returns at most ``limit`` distinct filers ordered
        by the response's natural relevance ranking.
        """
        if not name_query.strip():
            return []
        params = {
            "q": name_query.strip(),
            "forms": "13F-HR",
        }
        data = await self._get_json(f"{self.FULLTEXT_URL}/LATEST/search-index", params=params)
        hits = (data.get("hits") or {}).get("hits") or []
        seen: set[str] = set()
        out: list[FilerMetadata] = []
        for hit in hits:
            src = hit.get("_source") or {}
            # SEC fulltext returns ``ciks`` as a list of zero-padded strings,
            # and ``display_names`` as ["NAME (CIK 0001234567) (Type)"].
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            for idx, cik_raw in enumerate(ciks):
                cik = _pad_cik(str(cik_raw))
                if cik in seen:
                    continue
                seen.add(cik)
                display = names[idx] if idx < len(names) else cik
                # Trim "(CIK ...)" / "(Filer)" tails off display_name when present.
                short = display.split(" (CIK")[0].strip() or display
                out.append(FilerMetadata(cik=cik, name=short, legal_name=display))
                if len(out) >= limit:
                    return out
        return out

    async def get_filer_metadata(self, cik: str) -> FilerMetadata:
        """Fetch identity from ``data.sec.gov/submissions/CIK{padded}.json``."""
        padded = _pad_cik(cik)
        url = f"{self.DATA_URL}/submissions/CIK{padded}.json"
        data = await self._get_json(url)
        name = (data.get("name") or "").strip()
        if not name:
            # Some entities have only ``entityName``; fall back gracefully.
            name = (data.get("entityName") or padded).strip()
        return FilerMetadata(cik=padded, name=name, legal_name=name)

    async def list_filings_for_filer(
        self,
        cik: str,
        form_types: tuple[str, ...] = ("13F-HR", "13F-HR/A"),
        max_count: int = 4,
    ) -> list[FilingMetadata]:
        """List recent 13F filings, newest first.

        Reads the ``filings.recent`` block from the submissions endpoint
        (parallel arrays keyed by index). Filters by ``form_types``,
        truncates to ``max_count`` (default 4 → ~1 year of quarterlies,
        matching Phase 1 spec §8 Q8 default).

        For each filing kept, this method ALSO fetches the per-accession
        ``index.json`` directory listing and resolves the real
        ``<informationTable>`` XML URL via filename heuristics (see
        ``_resolve_infotable_url``). The submissions API's
        ``primaryDocument`` field for 13F-HR points at the XSL-rendered
        HTML view (``xslForm13F_X02/primary_doc.xml``) which is NOT
        parseable as XML and contains no infotable rows — we ignore it.

        Cost: one extra HTTP round-trip per filing (index.json). The
        rate limiter accounts for this. With ``max_count=4`` that's
        4 + 1 (submissions) = 5 requests per filer, well under the
        10 req/sec budget.
        """
        if max_count <= 0:
            return []
        padded = _pad_cik(cik)
        url = f"{self.DATA_URL}/submissions/CIK{padded}.json"
        data = await self._get_json(url)
        recent = ((data.get("filings") or {}).get("recent")) or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        period_of_report = recent.get("periodOfReport") or []
        filing_dates = recent.get("filingDate") or []

        cik_int = str(int(padded))  # archive URLs use the un-padded int
        out: list[FilingMetadata] = []
        for i in range(len(forms)):
            form = forms[i]
            if form not in form_types:
                continue
            accession_dashed = accessions[i] if i < len(accessions) else ""
            accession = accession_dashed.replace("-", "")
            if not accession:
                continue
            base = f"{self.BASE_URL}/Archives/edgar/data/{cik_int}/{accession}"
            cover_url = f"{base}/primary_doc.xml"

            # Resolve real infotable XML via the per-accession index.json.
            # On failure (network, schema drift), infotable_url is None;
            # caller logs+skips that filing.
            try:
                items = await self._fetch_filing_index(cik_int, accession)
            except EdgarTransientError as exc:
                logger.warning(
                    "edgar_index_fetch_failed",
                    cik=cik_int,
                    accession=accession,
                    error=str(exc),
                )
                items = []
            infotable_name = _resolve_infotable_filename(items)
            infotable_url = f"{base}/{infotable_name}" if infotable_name else None

            period_str = period_of_report[i] if i < len(period_of_report) else ""
            filed_str = filing_dates[i] if i < len(filing_dates) else ""
            out.append(
                FilingMetadata(
                    accession_number=accession,
                    form_type=form,
                    report_period_end=_parse_date(period_str),
                    filed_at=_parse_datetime(filed_str),
                    raw_xml_url=infotable_url,
                    cover_xml_url=cover_url,
                )
            )
            if len(out) >= max_count:
                break
        # ``filings.recent`` is already DESC by filing date but we sort
        # defensively in case SEC changes ordering.
        out.sort(key=lambda f: f.report_period_end, reverse=True)
        return out

    async def fetch_filing_xml(self, filing_url: str) -> str:
        """Download the XML body as text (charset-aware).

        Uses ``httpx`` ``text`` accessor which respects the
        ``Content-Type`` charset hint. Caller decides whether the bytes
        belong to ``primary_doc.xml`` or ``infotable.xml`` — we don't.
        """
        response = await self._request_with_retry("GET", filing_url)
        return response.text

    async def _fetch_filing_index(
        self, cik_int: str, accession_no_dashes: str
    ) -> list[dict[str, Any]]:
        """Fetch the per-accession directory listing from ``index.json``.

        Returns the ``directory.item`` list (each item has ``name``,
        ``type``, ``size``, ``last-modified``). Note: SEC's ``type``
        field is uninformative for 13F-HR (always ``text.gif``), so
        callers must rely on the filename to identify the infotable XML.
        """
        url = f"{self.BASE_URL}/Archives/edgar/data/{cik_int}/{accession_no_dashes}/index.json"
        data = await self._get_json(url)
        return ((data.get("directory") or {}).get("item")) or []

    # ── internal HTTP plumbing ──

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._request_with_retry("GET", url, params=params)
        # SEC sometimes responds JSON with text/plain content-type — call .json() directly.
        return response.json()

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError(
                "EdgarClient must be used as an async context manager "
                "(`async with EdgarClient(...) as c: ...`)"
            )

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.request(method, url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                wait_seconds = self._BACKOFF_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "edgar_request_transport_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt >= self._MAX_RETRIES:
                    break
                await asyncio.sleep(wait_seconds)
                continue

            if response.status_code == 429:
                # Respect Retry-After if present, else exponential.
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait_seconds = float(retry_after)
                    except ValueError:
                        wait_seconds = self._BACKOFF_BASE_SECONDS * (2**attempt)
                else:
                    wait_seconds = self._BACKOFF_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "edgar_rate_limited",
                    url=url,
                    attempt=attempt + 1,
                    retry_after=retry_after,
                    wait_seconds=wait_seconds,
                )
                if attempt >= self._MAX_RETRIES:
                    last_exc = EdgarTransientError(
                        f"EDGAR rate-limited after {self._MAX_RETRIES + 1} attempts"
                    )
                    break
                await asyncio.sleep(wait_seconds)
                continue

            if 500 <= response.status_code < 600:
                wait_seconds = self._BACKOFF_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "edgar_server_error",
                    url=url,
                    status=response.status_code,
                    attempt=attempt + 1,
                )
                last_exc = EdgarTransientError(f"EDGAR returned {response.status_code} after retry")
                if attempt >= self._MAX_RETRIES:
                    break
                await asyncio.sleep(wait_seconds)
                continue

            # 4xx (other than 429) — caller mistake, do not retry.
            if 400 <= response.status_code < 500:
                response.raise_for_status()

            return response

        # Exhausted retries.
        if isinstance(last_exc, EdgarTransientError):
            raise last_exc
        raise EdgarTransientError(
            f"EDGAR request failed after {self._MAX_RETRIES + 1} attempts: {last_exc!r}"
        )


# ───────────────────────── private helpers ─────────────────────────


def _resolve_infotable_filename(items: list[dict[str, Any]]) -> str | None:
    """Pick the infotable XML filename from a filing-index ``item`` list.

    Heuristic (filename-based — SEC's ``item.type`` is uninformative for
    13F-HR, always ``text.gif``):

    1. Any ``.xml`` whose lowercased basename contains ``infotable``
       or ``informationtable`` (e.g. ``infotable.xml``,
       ``form13fInfoTable.xml``).
    2. Otherwise: the first ``.xml`` that is **not** ``primary_doc.xml``
       and does **not** contain a directory separator (i.e. exclude
       ``xslForm13F_X02/primary_doc.xml`` which is the XSL renderer
       output, not a real co-resident file in the listing — but
       defensive belt-and-suspenders).

    Returns ``None`` if no candidate is found — caller treats that as
    "no holdings ingestable for this filing".
    """
    candidates: list[str] = []
    for item in items:
        name = (item.get("name") or "").strip()
        if not name.lower().endswith(".xml"):
            continue
        if "/" in name:
            continue
        if name == "primary_doc.xml":
            continue
        candidates.append(name)

    # Pass 1: prefer explicit infotable naming.
    for name in candidates:
        lname = name.lower()
        if "infotable" in lname or "informationtable" in lname:
            return name

    # Pass 2: any remaining .xml — accession-derived filenames like
    # ``53405.xml`` land here (Berkshire convention).
    if candidates:
        return candidates[0]
    return None


def _pad_cik(cik: str) -> str:
    """Zero-pad CIK to 10 digits — the canonical SEC submissions form."""
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        raise ValueError(f"invalid CIK (no digits): {cik!r}")
    return digits.zfill(10)


def _parse_date(s: str) -> date:
    """Parse SEC ``YYYY-MM-DD`` date strings, tolerant of empty input."""
    if not s:
        return date.min
    try:
        return date.fromisoformat(s)
    except ValueError:
        return date.min


def _parse_datetime(s: str) -> datetime:
    """Parse SEC date/datetime strings. Most fields are date-only.

    SEC ``filings.recent.filingDate`` is YYYY-MM-DD; we lift to midnight.
    Some other endpoints emit full timestamps — handled via fromisoformat.
    """
    if not s:
        return datetime.min
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        d = date.fromisoformat(s)
        return datetime(d.year, d.month, d.day)
    except ValueError:
        return datetime.min
