"""Integration tests for `app.services.institutional.scheduled_refresh_job`.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2 (refresh policy) + §11 R6 (idempotency) + Q1 (Pro daily / Basic
weekly / Free on-demand only).

Cases:

  S01 FREE tier is rejected by refresh_for_tier (raises ValueError).
  S02 PRO daily refresh actually refreshes a subscribed filer + counts.
  S03 Filer refreshed within skip window is *skipped*, not refreshed.
  S04 Refresh delegates the EDGAR fetch through F13FilingService
      (asserted via MockEdgarClient call counters).
  S05 F13RefreshInFlight (lock held by manual refresh) is counted as
      `skipped`, not `errors`.
  S06 The aggregate stats dict reports every documented key.
  S07 BASIC weekly skip window is 6 days (so a filer with
      latest_filing_date == 5 days ago is skipped, 7 days ago is
      refreshed).
  S08 No subscriptions on this tier → empty stats (zeros everywhere).
  S09 Smoke: app lifespan registers `13f_pro_daily` + `13f_basic_weekly`.

`MockEdgarClient` is intentionally duplicated from
`test_institutional_services.py` rather than imported, so this file
remains self-contained — pytest discovery order can mark a test file's
helpers unimportable for siblings that diverge on conftest.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.subscription import F13UserSubscription
from app.models.enums import UserTier
from app.models.user import User
from app.modules.institutional.edgar_client import (
    FilerMetadata,
    FilingMetadata,
)
from app.services.institutional.filing_service import F13FilingService
from app.services.institutional.scheduled_refresh_job import (
    daily_pro_refresh,
    refresh_for_tier,
    weekly_basic_refresh,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── MockEdgarClient ────────────────────────────────────────────────────────


class MockEdgarClient:
    """Async-context-manager-compatible EDGAR test double.

    Mirrors the shape used in `test_institutional_services.py`. We add
    no-op ``__aenter__`` / ``__aexit__`` so the scheduler entrypoints
    (which open a real ``EdgarClient`` via ``async with``) could in
    principle take this directly — but the tests inject the *open*
    client into ``refresh_for_tier`` and never hit the entrypoint
    wrapper, by design (the wrapper opens its own DB session, which
    would bypass the in-memory ``db_session`` fixture).
    """

    def __init__(self) -> None:
        self._filings_responses: dict[str, list[FilingMetadata]] = {}
        self._xml_responses: dict[str, str] = {}
        self._search_response: list[FilerMetadata] = []
        self.calls_list_filings: list[str] = []
        self.calls_fetch_xml: list[str] = []

    def set_filings_response(
        self, cik: str, filings: list[FilingMetadata]
    ) -> None:
        self._filings_responses[cik] = filings

    def set_xml_response(self, url: str, xml: str) -> None:
        self._xml_responses[url] = xml

    async def __aenter__(self) -> MockEdgarClient:  # pragma: no cover
        return self

    async def __aexit__(self, *exc_info: object) -> None:  # pragma: no cover
        return None

    async def search_filers_by_name(
        self, name_query: str, limit: int = 20
    ) -> list[FilerMetadata]:  # pragma: no cover - unused in this file
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


# ── helpers ────────────────────────────────────────────────────────────────


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
    latest_filing_date: date | None = None,
) -> F13Filer:
    f = F13Filer(cik=cik, name=name)
    if latest_filing_date is not None:
        f.latest_filing_date = latest_filing_date
    db.add(f)
    await db.commit()
    await db.refresh(f)
    # Reset the class-scope per-filer lock so cross-test bleed is impossible.
    F13FilingService._locks.pop(f.id, None)
    return f


async def _subscribe(
    db: AsyncSession, user_id: int, filer_id: int
) -> F13UserSubscription:
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


# A fixed "now" lets us write the skip-window assertions against
# deterministic dates (no leakage from `datetime.now`).
_FIXED_NOW = datetime(2026, 5, 19, 6, 0, tzinfo=UTC)


# ═════════════════════════════════════════════════════════════════════════════
# S01: FREE tier is rejected
# ═════════════════════════════════════════════════════════════════════════════


async def test_refresh_for_tier_rejects_free(
    db_session: AsyncSession,
) -> None:
    """FREE users are on-demand-only by Q1; the helper must refuse."""
    edgar = MockEdgarClient()
    with pytest.raises(ValueError, match="FREE"):
        await refresh_for_tier(
            db_session,
            edgar,  # type: ignore[arg-type]
            UserTier.FREE,
            skip_recent_hours=12,
            now=_FIXED_NOW,
        )


# ═════════════════════════════════════════════════════════════════════════════
# S02: PRO daily path refreshes a subscribed filer
# ═════════════════════════════════════════════════════════════════════════════


async def test_pro_daily_refreshes_subscribed_filer(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "pro1@x.com", "pro1", tier=UserTier.PRO)
    filer = await _mk_filer(db_session, cik="0008000001")
    await _subscribe(db_session, user.id, filer.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0008000001",
        [_mk_filing_meta("acc-fresh", date(2026, 3, 31))],
    )

    result = await daily_pro_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]
    await db_session.commit()

    assert result["users_processed"] == 1
    assert result["filers_refreshed"] == 1
    assert result["filings_added"] == 1
    assert result["holdings_added"] == 1  # 1 infotable row in MINIMAL XML
    assert result["skipped"] == 0
    assert result["errors"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# S03: Skip filers refreshed within the per-tier window
# ═════════════════════════════════════════════════════════════════════════════


async def test_refresh_skips_recently_refreshed_filer(
    db_session: AsyncSession,
) -> None:
    """latest_filing_date >= now - 12h → skipped, edgar untouched."""
    user = await _mk_user(db_session, "pro2@x.com", "pro2", tier=UserTier.PRO)
    # latest_filing_date == today (within 12h of `_FIXED_NOW`).
    filer = await _mk_filer(
        db_session,
        cik="0008000002",
        latest_filing_date=_FIXED_NOW.date(),
    )
    await _subscribe(db_session, user.id, filer.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response("0008000002", [])

    result = await daily_pro_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]
    await db_session.commit()

    assert result["filers_refreshed"] == 0
    assert result["skipped"] == 1
    # EDGAR list_filings was never called because we skipped earlier.
    assert edgar.calls_list_filings == []


# ═════════════════════════════════════════════════════════════════════════════
# S04: Refresh goes through EdgarClient via F13FilingService
# ═════════════════════════════════════════════════════════════════════════════


async def test_refresh_calls_edgar_via_filing_service(
    db_session: AsyncSession,
) -> None:
    """Cron job must route through `F13FilingService.refresh_filer`,
    which is what surfaces the EDGAR call. We assert the mock saw
    both the `list_filings_for_filer` and `fetch_filing_xml` calls.
    """
    user = await _mk_user(db_session, "pro3@x.com", "pro3", tier=UserTier.PRO)
    filer = await _mk_filer(db_session, cik="0008000003")
    await _subscribe(db_session, user.id, filer.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0008000003",
        [
            _mk_filing_meta(
                "acc-edgar", date(2026, 3, 31),
                url="https://example.com/acc-edgar.xml",
            )
        ],
    )
    edgar.set_xml_response(
        "https://example.com/acc-edgar.xml", _MINIMAL_INFOTABLE_XML
    )

    await daily_pro_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]
    await db_session.commit()

    assert edgar.calls_list_filings == ["0008000003"]
    assert edgar.calls_fetch_xml == ["https://example.com/acc-edgar.xml"]


# ═════════════════════════════════════════════════════════════════════════════
# S05: F13RefreshInFlight is counted as `skipped`, not `errors`
# ═════════════════════════════════════════════════════════════════════════════


async def test_concurrent_refresh_counted_as_skipped(
    db_session: AsyncSession,
) -> None:
    """If a manual refresh holds the per-filer lock, the cron job loses
    the race gracefully — that's the *correct* outcome, not an error.
    """
    user = await _mk_user(db_session, "pro4@x.com", "pro4", tier=UserTier.PRO)
    filer = await _mk_filer(db_session, cik="0008000004")
    await _subscribe(db_session, user.id, filer.id)

    # Pre-acquire the per-filer lock to simulate an in-flight manual refresh.
    # `F13FilingService._locks` is the class-scope dict the service uses
    # for anti-concurrency.
    lock = asyncio.Lock()
    F13FilingService._locks[filer.id] = lock
    await lock.acquire()

    try:
        edgar = MockEdgarClient()
        edgar.set_filings_response("0008000004", [])

        result = await daily_pro_refresh(
            db_session, edgar, now=_FIXED_NOW  # type: ignore[arg-type]
        )
        await db_session.commit()

        assert result["filers_refreshed"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == 0
    finally:
        lock.release()
        F13FilingService._locks.pop(filer.id, None)


# ═════════════════════════════════════════════════════════════════════════════
# S06: Aggregate stats expose every documented key
# ═════════════════════════════════════════════════════════════════════════════


async def test_aggregate_stats_returned(
    db_session: AsyncSession,
) -> None:
    """Stats dict carries the full set of observability keys."""
    user = await _mk_user(db_session, "pro5@x.com", "pro5", tier=UserTier.PRO)
    filer = await _mk_filer(db_session, cik="0008000005")
    await _subscribe(db_session, user.id, filer.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response("0008000005", [])

    result = await daily_pro_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]
    expected_keys = {
        "users_processed",
        "filers_refreshed",
        "filings_added",
        "holdings_added",
        "skipped",
        "errors",
    }
    assert set(result.keys()) == expected_keys
    assert all(isinstance(v, int) for v in result.values())


# ═════════════════════════════════════════════════════════════════════════════
# S07: BASIC weekly skip window is 6 days
# ═════════════════════════════════════════════════════════════════════════════


async def test_basic_weekly_skips_recent_within_6_days(
    db_session: AsyncSession,
) -> None:
    """Filer refreshed 5d ago → skipped. Filer refreshed 7d ago → refreshed."""
    # 5d-old filer subscribed by user A — should be skipped on the basic run.
    user_a = await _mk_user(
        db_session, "basic1@x.com", "basic1", tier=UserTier.BASIC
    )
    filer_recent = await _mk_filer(
        db_session,
        cik="0009000001",
        latest_filing_date=(_FIXED_NOW - timedelta(days=5)).date(),
    )
    await _subscribe(db_session, user_a.id, filer_recent.id)

    # 7d-old filer subscribed by user B — should be refreshed.
    user_b = await _mk_user(
        db_session, "basic2@x.com", "basic2", tier=UserTier.BASIC
    )
    filer_stale = await _mk_filer(
        db_session,
        cik="0009000002",
        latest_filing_date=(_FIXED_NOW - timedelta(days=7)).date(),
    )
    await _subscribe(db_session, user_b.id, filer_stale.id)

    edgar = MockEdgarClient()
    edgar.set_filings_response("0009000002", [])  # empty → 0 new filings

    result = await weekly_basic_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]
    await db_session.commit()

    assert result["skipped"] == 1
    # `filers_refreshed` counts filers we actually hit refresh on (even
    # if 0 filings were added) — that's the semantic we documented.
    assert result["filers_refreshed"] == 1
    # Only the stale filer's CIK should have hit EDGAR.
    assert edgar.calls_list_filings == ["0009000002"]


# ═════════════════════════════════════════════════════════════════════════════
# S08: No subscriptions on this tier → empty stats
# ═════════════════════════════════════════════════════════════════════════════


async def test_no_subscriptions_returns_empty_stats(
    db_session: AsyncSession,
) -> None:
    """Empty cohort means zero work — every counter must be 0."""
    # Create a PRO user with NO subscriptions. The JOIN in refresh_for_tier
    # drops users with zero subs, so they never get counted.
    await _mk_user(db_session, "lonely@x.com", "lonely", tier=UserTier.PRO)

    edgar = MockEdgarClient()
    result = await daily_pro_refresh(db_session, edgar, now=_FIXED_NOW)  # type: ignore[arg-type]

    assert result == {
        "users_processed": 0,
        "filers_refreshed": 0,
        "filings_added": 0,
        "holdings_added": 0,
        "skipped": 0,
        "errors": 0,
    }


# ═════════════════════════════════════════════════════════════════════════════
# S09: Smoke — app lifespan registers both 13F cron jobs
# ═════════════════════════════════════════════════════════════════════════════


async def test_app_lifespan_registers_scheduler_jobs() -> None:
    """Verify the lifespan_scheduler context registers both jobs.

    We bypass the full app lifespan (which starts AutoSyncScheduler /
    job_worker / Prometheus too) and just enter the 13F scheduler
    context directly. That keeps the test fast and avoids the heavy
    setup of `create_app()`.
    """
    import app.scheduler as scheduler_mod
    from app.scheduler import (
        JOB_ID_BASIC_WEEKLY,
        JOB_ID_PRO_DAILY,
        get_scheduler,
        lifespan_scheduler,
    )

    # Reset singleton so a previous test (or import) doesn't leak state.

    scheduler_mod._scheduler = None  # type: ignore[attr-defined]

    async with lifespan_scheduler() as scheduler:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert JOB_ID_PRO_DAILY in job_ids
        assert JOB_ID_BASIC_WEEKLY in job_ids
        # Same singleton accessible without going through the context.
        assert get_scheduler() is scheduler
        # While the context is active the scheduler is running.
        assert scheduler.running

    # Note: we deliberately don't assert `not scheduler.running` after
    # exit. AsyncIOScheduler.shutdown(wait=False) returns immediately
    # but the internal state transition can lag a few microseconds on
    # the event loop — the contract we care about is "started + jobs
    # registered inside the context," not the precise shutdown timing.
