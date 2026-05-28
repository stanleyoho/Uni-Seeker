"""Integration tests for ``F13FilingsSyncTask`` (sync_manager wire-up).

Wave 2 Axis R2 — verifies that the new sync task at
``app.modules.sync_manager.tasks.f13_filings.F13FilingsSyncTask``:

  T01 returns a clean ``SyncResult`` with zeros when no users / subs exist
      (defensive case — production may launch with empty f13_filers).
  T02 ingests a new filing for a PRO-tier subscribed filer and reports
      the per-tier stats correctly (filings_added → records_synced,
      filers_refreshed → stocks_processed).
  T03 is registered in ``SyncScheduler._TASK_ORDER`` and ``._tasks``
      so ``POST /api/v1/sync/run/f13_filings`` will dispatch to it.

We mock ``EdgarClient`` by patching the symbol the task imports at
runtime (``app.modules.sync_manager.tasks.f13_filings.EdgarClient``)
because the task constructs the client itself inside ``run()`` — the
shared MockEdgarClient pattern from ``test_scheduled_refresh_job.py`` is
duplicated here for the same self-containment reason cited in that file.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.subscription import F13UserSubscription
from app.models.enums import UserTier
from app.models.user import User
from app.modules.institutional.edgar_client import FilerMetadata, FilingMetadata
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.scheduler import SyncScheduler
from app.modules.sync_manager.tasks.f13_filings import F13FilingsSyncTask
from app.services.institutional.filing_service import F13FilingService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── MockEdgarClient (mirrors test_scheduled_refresh_job.py) ───────────────


class MockEdgarClient:
    """Async-context-manager double for ``EdgarClient``.

    Honours the same surface the production client exposes to
    ``F13FilingService.refresh_filer`` so we can swap it in via
    monkeypatch without touching any service code.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        # Accept (and ignore) constructor args so the patch can mirror
        # the production signature: ``EdgarClient(user_agent=...)``.
        del args, kwargs
        self._filings_responses: dict[str, list[FilingMetadata]] = {}
        self._xml_responses: dict[str, str] = {}
        self._search_response: list[FilerMetadata] = []
        self.calls_list_filings: list[str] = []
        self.calls_fetch_xml: list[str] = []

    def set_filings_response(self, cik: str, filings: list[FilingMetadata]) -> None:
        self._filings_responses[cik] = filings

    def set_xml_response(self, url: str, xml: str) -> None:
        self._xml_responses[url] = xml

    async def __aenter__(self) -> MockEdgarClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def search_filers_by_name(
        self, name_query: str, limit: int = 20
    ) -> list[FilerMetadata]:  # pragma: no cover - unused here
        return list(self._search_response)[:limit]

    async def list_filings_for_filer(
        self,
        cik: str,
        form_types: tuple[str, ...] = ("13F-HR", "13F-HR/A"),
        max_count: int = 4,
    ) -> list[FilingMetadata]:
        self.calls_list_filings.append(cik)
        return list(self._filings_responses.get(cik, []))[:max_count]

    async def fetch_filing_xml(self, filing_url: str) -> str:
        self.calls_fetch_xml.append(filing_url)
        return self._xml_responses.get(filing_url, _MINIMAL_INFOTABLE_XML)


_MINIMAL_INFOTABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>5000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>100</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>100</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
"""


# ── helpers (mirror test_scheduled_refresh_job.py shape) ──────────────────


async def _mk_user(
    db: AsyncSession,
    email: str,
    username: str,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_filer(
    db: AsyncSession,
    cik: str,
    name: str = "Test Filer",
) -> F13Filer:
    f = F13Filer(cik=cik, name=name)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    # Reset the class-scope per-filer lock so cross-test bleed is impossible.
    F13FilingService._locks.pop(f.id, None)
    return f


async def _subscribe(db: AsyncSession, user_id: int, filer_id: int) -> F13UserSubscription:
    sub = F13UserSubscription(user_id=user_id, filer_id=filer_id)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


def _mk_filing_meta(
    accession: str,
    period: date,
    url: str | None = None,
    form_type: str = "13F-HR",
) -> FilingMetadata:
    return FilingMetadata(
        accession_number=accession,
        form_type=form_type,
        report_period_end=period,
        filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
        raw_xml_url=url or f"https://example.com/{accession}/infotable.xml",
    )


# ═══════════════════════════════════════════════════════════════════════════
# T01: empty subscription table → zero-row SyncResult
# ═══════════════════════════════════════════════════════════════════════════


async def test_run_no_subscriptions_returns_zeros(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No users / no subs → run completes cleanly with zero records.

    This is the defensive case the task spec calls out: a freshly
    deployed env with the schema in place but the f13_filers /
    f13_user_subscriptions tables empty.
    """
    edgar = MockEdgarClient()
    monkeypatch.setattr(
        "app.modules.sync_manager.tasks.f13_filings.EdgarClient",
        lambda *a, **kw: edgar,
    )

    task = F13FilingsSyncTask()
    result = await task.run(db_session, RateLimiter())

    assert result.dataset == "f13_filings"
    assert result.records_synced == 0
    assert result.stocks_processed == 0
    assert result.errors == 0
    assert result.stopped_reason == "completed"
    # EDGAR was never asked for any CIK.
    assert edgar.calls_list_filings == []


# ═══════════════════════════════════════════════════════════════════════════
# T02: PRO subscriber's filer gets refreshed, counts roll up correctly
# ═══════════════════════════════════════════════════════════════════════════


async def test_run_pro_subscriber_ingests_one_filing(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path — PRO user with one subscribed filer, one new filing.

    Verifies:
      - records_synced reflects the one filing that was added
      - stocks_processed reflects the one filer that was refreshed
      - errors == 0
      - the EDGAR mock was actually called with the filer's CIK
    """
    user = await _mk_user(db_session, "pro1@x.com", "pro1", tier=UserTier.PRO)
    filer = await _mk_filer(db_session, cik="0008000099")
    await _subscribe(db_session, user.id, filer.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0008000099",
        [_mk_filing_meta("acc-newrun", date(2026, 3, 31))],
    )
    monkeypatch.setattr(
        "app.modules.sync_manager.tasks.f13_filings.EdgarClient",
        lambda *a, **kw: edgar,
    )

    task = F13FilingsSyncTask()
    result = await task.run(db_session, RateLimiter())
    await db_session.commit()

    assert result.dataset == "f13_filings"
    assert result.records_synced == 1  # one new filing
    assert result.stocks_processed == 1  # one filer refreshed
    assert result.errors == 0
    assert result.stopped_reason == "completed"
    assert "0008000099" in edgar.calls_list_filings


# ═══════════════════════════════════════════════════════════════════════════
# T03: scheduler registration smoke test
# ═══════════════════════════════════════════════════════════════════════════


def test_scheduler_registers_f13_filings() -> None:
    """``SyncScheduler`` must surface ``f13_filings`` so the dynamic
    dispatch endpoint can route to it.

    We assert on both the public ``task_names`` list (used by the
    ``POST /api/v1/sync/run/{task_name}`` validator) and on the concrete
    type so a future rename of the task class is caught at test time.
    """
    scheduler = SyncScheduler()
    assert "f13_filings" in scheduler.task_names
    assert isinstance(scheduler._tasks["f13_filings"], F13FilingsSyncTask)
