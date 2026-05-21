"""Integration tests for institutional 13F services (Phase 1 / UNI-F13-001 Batch B2).

Layout (~18 cases per task brief):

  SubscriptionService     : 6  subscribe happy / quota / duplicate / unsubscribe ok / unsubscribe missing / list isolation
  FilerSearchService      : 1  local + edgar merge with mock
  FilingService refresh   : 4  happy / idempotency / updates filer.latest_* / concurrent → 429
  FilingService reads     : 2  list_filings access control / compute_diff
  CrossStockService       : 2  Free blocked / Pro returns data
  Audit                   : 3  subscribe / unsubscribe / refresh produce audit rows

`MockEdgarClient` is the test double for `EdgarClient` used by both
`FilerSearchService` and `FilingService`. It satisfies the duck-typed
contract those services consume (`search_filers_by_name`,
`list_filings_for_filer`, `fetch_filing_xml`) and provides simple
`set_*_response` setters per the task brief.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.stock import Stock
from app.models.user import User
from app.modules.institutional.edgar_client import (
    FilerMetadata,
    FilingMetadata,
)
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
    F13UserSubscriptionRepo,
)
from app.services.institutional import (
    F13CrossStockService,
    F13FilerNotFound,
    F13FilerSearchService,
    F13FilingNotFound,
    F13FilingService,
    F13RefreshInFlight,
    F13SubscriptionExists,
    F13SubscriptionService,
    F13TierFeatureUnavailable,
    F13TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── MockEdgarClient ─────────────────────────────────────────────────────────


class MockEdgarClient:
    """Test double for `EdgarClient`.

    Satisfies the contract that `F13FilingService` + `F13FilerSearchService`
    consume — `search_filers_by_name`, `list_filings_for_filer`,
    `fetch_filing_xml`. State is configured via the `set_*_response`
    setters per the task brief.

    Counters (`calls_*`) let assertions verify mock interactions without
    pulling in `unittest.mock.AsyncMock` semantics.
    """

    def __init__(self) -> None:
        self._filings_responses: dict[str, list[FilingMetadata]] = {}
        self._xml_responses: dict[str, str] = {}
        self._search_response: list[FilerMetadata] = []
        self.calls_list_filings: list[str] = []
        self.calls_fetch_xml: list[str] = []
        self.calls_search: list[str] = []

    # configuration ----------------------------------------------------

    def set_filings_response(
        self, cik: str, filings: list[FilingMetadata]
    ) -> None:
        self._filings_responses[cik] = filings

    def set_xml_response(self, url: str, xml: str) -> None:
        self._xml_responses[url] = xml

    def set_search_response(self, hits: list[FilerMetadata]) -> None:
        self._search_response = list(hits)

    # contract --------------------------------------------------------

    async def search_filers_by_name(
        self, name_query: str, limit: int = 20
    ) -> list[FilerMetadata]:
        self.calls_search.append(name_query)
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


# ── Fixtures / helpers ─────────────────────────────────────────────────────


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


async def _count_audit(
    db: AsyncSession, action: str, user_id: int
) -> int:
    result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == action, AuditLog.user_id == user_id
        )
    )
    return int(result.scalar() or 0)


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
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>3000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>50</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
"""


# ═════════════════════════════════════════════════════════════════════════════
# F13SubscriptionService (6 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_subscribe_happy_path_creates_filer_and_sub(
    db_session: AsyncSession,
) -> None:
    """Subscribing by CIK string creates the filer row + the sub + audit."""
    user = await _mk_user(db_session, "ss1@x.com", "ss1")
    svc = F13SubscriptionService(db_session, user)

    filer = await svc.subscribe(
        cik_or_filer_id="0001234567",
        name="Acme LP",
        legal_name="ACME LP",
    )
    await db_session.commit()

    assert filer.cik == "0001234567"
    assert filer.name == "Acme LP"

    # 2nd attempt to same filer (different name ignored) raises 409.
    with pytest.raises(F13SubscriptionExists) as exc:
        await svc.subscribe(
            cik_or_filer_id="0001234567", name="Acme LP"
        )
    assert exc.value.filer_id == filer.id

    # audit log written
    assert (
        await _count_audit(db_session, "f13_filer_subscribed", user.id)
        == 1
    )


async def test_subscribe_free_tier_quota_blocks_second(
    db_session: AsyncSession,
) -> None:
    """FREE.max_tracked_filers = 1 → 2nd subscribe raises TierLimitExceeded."""
    user = await _mk_user(
        db_session, "ss2@x.com", "ss2", tier=UserTier.FREE
    )
    svc = F13SubscriptionService(db_session, user)

    with patch(
        "app.services.institutional.subscription_service.settings"
    ) as s:
        s.enable_monetization = True
        # First subscribe allowed (count 0 → 1, limit 1: 0 < 1).
        await svc.subscribe(
            cik_or_filer_id="0001111111", name="Filer One"
        )
        await db_session.commit()

        with pytest.raises(F13TierLimitExceeded) as exc:
            await svc.subscribe(
                cik_or_filer_id="0002222222", name="Filer Two"
            )
        assert exc.value.limit_key == "max_tracked_filers"
        assert exc.value.limit == 1


async def test_subscribe_by_int_filer_id_404(
    db_session: AsyncSession,
) -> None:
    """Passing int that doesn't exist raises F13FilerNotFound."""
    user = await _mk_user(db_session, "ss3@x.com", "ss3")
    svc = F13SubscriptionService(db_session, user)

    with pytest.raises(F13FilerNotFound):
        await svc.subscribe(cik_or_filer_id=999999)


async def test_unsubscribe_happy_then_missing(
    db_session: AsyncSession,
) -> None:
    """unsubscribe returns None on hit + audit; raises on missing."""
    user = await _mk_user(db_session, "ss4@x.com", "ss4")
    svc = F13SubscriptionService(db_session, user)
    filer = await svc.subscribe(
        cik_or_filer_id="0001000004", name="Sub-Test"
    )
    await db_session.commit()

    await svc.unsubscribe(filer.id)
    await db_session.commit()
    assert (
        await _count_audit(db_session, "f13_filer_unsubscribed", user.id)
        == 1
    )

    # Second unsubscribe raises.
    with pytest.raises(F13FilerNotFound):
        await svc.unsubscribe(filer.id)


async def test_list_subscriptions_cross_user_isolation(
    db_session: AsyncSession,
) -> None:
    """User B does not see User A's subscriptions even on a shared filer."""
    a = await _mk_user(db_session, "ssa@x.com", "ssa")
    b = await _mk_user(db_session, "ssb@x.com", "ssb")
    svc_a = F13SubscriptionService(db_session, a)
    svc_b = F13SubscriptionService(db_session, b)

    await svc_a.subscribe(
        cik_or_filer_id="0009000001", name="Shared Fund"
    )
    await db_session.commit()

    assert len(await svc_a.list_subscriptions()) == 1
    assert await svc_b.list_subscriptions() == []


async def test_subscribe_str_requires_name(
    db_session: AsyncSession,
) -> None:
    """Subscribing by str CIK without name raises ValueError (NOT NULL)."""
    user = await _mk_user(db_session, "ss6@x.com", "ss6")
    svc = F13SubscriptionService(db_session, user)
    with pytest.raises(ValueError):
        await svc.subscribe(cik_or_filer_id="0001000006", name=None)


# ═════════════════════════════════════════════════════════════════════════════
# F13FilerSearchService (1 case — local + edgar merge)
# ═════════════════════════════════════════════════════════════════════════════


async def test_filer_search_merges_local_and_edgar(
    db_session: AsyncSession,
) -> None:
    """Local hit returns first with is_locally_known=True; EDGAR fills rest."""
    user = await _mk_user(db_session, "fs1@x.com", "fs1")

    # Seed a local filer with name matching the query
    await F13FilerRepo(db_session).create(
        cik="0001000111", name="Berkshire Hathaway"
    )
    await db_session.commit()

    edgar = MockEdgarClient()
    edgar.set_search_response([
        FilerMetadata(
            cik="0001000111",  # dup with local → should be deduped
            name="Berkshire Hathaway",
            legal_name="BERKSHIRE HATHAWAY INC",
        ),
        FilerMetadata(
            cik="0001000222",
            name="Berkshire Partners",
            legal_name="BERKSHIRE PARTNERS LLC",
        ),
    ])

    svc = F13FilerSearchService(db_session, user, edgar)
    hits = await svc.search_filers("berkshire", limit=10)

    assert len(hits) == 2
    assert hits[0]["is_locally_known"] is True
    assert hits[0]["cik"] == "0001000111"
    assert hits[1]["is_locally_known"] is False
    assert hits[1]["cik"] == "0001000222"
    assert edgar.calls_search == ["berkshire"]


# ═════════════════════════════════════════════════════════════════════════════
# F13FilingService — refresh (4 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def _setup_subscribed_filer(
    db_session: AsyncSession,
    user: User,
    cik: str = "0007000001",
) -> Any:
    """Helper: create filer, subscribe user, return filer."""
    sub_svc = F13SubscriptionService(db_session, user)
    filer = await sub_svc.subscribe(cik_or_filer_id=cik, name="Refreshable")
    await db_session.commit()
    # Reset filing_service per-filer lock to avoid cross-test bleed.
    F13FilingService._locks.pop(filer.id, None)
    return filer


async def test_refresh_filer_happy_path(
    db_session: AsyncSession,
) -> None:
    """refresh inserts 2 new filings + their holdings; returns counts."""
    user = await _mk_user(db_session, "rf1@x.com", "rf1")
    filer = await _setup_subscribed_filer(db_session, user, cik="0007111111")

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0007111111",
        [
            _mk_filing_meta(
                "acc-q4", date(2025, 12, 31),
                url="https://example.com/q4.xml",
            ),
            _mk_filing_meta(
                "acc-q3", date(2025, 9, 30),
                url="https://example.com/q3.xml",
            ),
        ],
    )
    edgar.set_xml_response(
        "https://example.com/q4.xml", _MINIMAL_INFOTABLE_XML
    )
    edgar.set_xml_response(
        "https://example.com/q3.xml", _MINIMAL_INFOTABLE_XML
    )

    svc = F13FilingService(db_session, user, edgar)
    result = await svc.refresh_filer(filer.id, max_quarters=4)
    await db_session.commit()

    assert result["filings_added"] == 2
    # 2 holdings per filing × 2 filings = 4
    assert result["holdings_added"] == 4

    stored = await F13FilingRepo(db_session).list_by_filer(filer.id)
    assert {f.accession_number for f in stored} == {"acc-q4", "acc-q3"}


async def test_refresh_filer_idempotent_does_not_dup(
    db_session: AsyncSession,
) -> None:
    """Re-running refresh on same accession set adds 0 rows."""
    user = await _mk_user(db_session, "rf2@x.com", "rf2")
    filer = await _setup_subscribed_filer(db_session, user, cik="0007222222")

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0007222222",
        [_mk_filing_meta("dup-acc", date(2025, 12, 31))],
    )

    svc = F13FilingService(db_session, user, edgar)
    first = await svc.refresh_filer(filer.id)
    await db_session.commit()
    assert first["filings_added"] == 1

    second = await svc.refresh_filer(filer.id)
    await db_session.commit()
    assert second["filings_added"] == 0
    assert second["holdings_added"] == 0


async def test_refresh_filer_updates_latest_aum(
    db_session: AsyncSession,
) -> None:
    """After refresh the filer.latest_* columns reflect the freshest filing."""
    user = await _mk_user(db_session, "rf3@x.com", "rf3")
    filer = await _setup_subscribed_filer(db_session, user, cik="0007333333")

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0007333333",
        [
            _mk_filing_meta(
                "fresh-acc", date(2025, 12, 31),
                url="https://example.com/fresh.xml",
            ),
        ],
    )
    edgar.set_xml_response(
        "https://example.com/fresh.xml", _MINIMAL_INFOTABLE_XML
    )

    svc = F13FilingService(db_session, user, edgar)
    await svc.refresh_filer(filer.id)
    await db_session.commit()

    fresh = await F13FilerRepo(db_session).get_by_id(filer.id)
    assert fresh is not None
    # MINIMAL XML has 2 holdings each with value*1000 = 5_000_000 + 3_000_000.
    assert fresh.latest_total_value_usd == Decimal("8000000")
    assert fresh.latest_position_count == 2
    assert fresh.latest_filing_date == date(2025, 12, 31)


async def test_refresh_concurrent_raises_in_flight(
    db_session: AsyncSession,
) -> None:
    """A second concurrent refresh on the same filer raises 429."""
    user = await _mk_user(db_session, "rf4@x.com", "rf4")
    filer = await _setup_subscribed_filer(db_session, user, cik="0007444444")

    edgar = MockEdgarClient()
    edgar.set_filings_response("0007444444", [])

    svc = F13FilingService(db_session, user, edgar)

    # Manually grab the per-filer lock to simulate an in-flight refresh.
    lock = await svc._get_lock(filer.id)
    await lock.acquire()
    try:
        with pytest.raises(F13RefreshInFlight) as exc:
            await svc.refresh_filer(filer.id)
        assert exc.value.filer_id == filer.id
    finally:
        lock.release()


# ═════════════════════════════════════════════════════════════════════════════
# F13FilingService — reads (2 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_list_filings_requires_subscription(
    db_session: AsyncSession,
) -> None:
    """list_filings_for_filer raises NotFound when user not subscribed."""
    user_a = await _mk_user(db_session, "lf1a@x.com", "lf1a")
    user_b = await _mk_user(db_session, "lf1b@x.com", "lf1b")
    filer = await _setup_subscribed_filer(
        db_session, user_a, cik="0007555555"
    )
    # Add a filing manually so we know the listing would have content.
    await F13FilingRepo(db_session).create(
        filer_id=filer.id,
        accession_number="acc1",
        form_type="13F-HR",
        report_period_end=date(2025, 12, 31),
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("1"),
        options_notional_usd=Decimal("0"),
        total_positions=1,
        raw_xml_url="x",
    )
    await db_session.commit()

    edgar = MockEdgarClient()
    svc_a = F13FilingService(db_session, user_a, edgar)
    svc_b = F13FilingService(db_session, user_b, edgar)

    rows = await svc_a.list_filings_for_filer(filer.id)
    assert len(rows) == 1

    # User B is not subscribed — must NOT see the filing.
    with pytest.raises(F13FilerNotFound):
        await svc_b.list_filings_for_filer(filer.id)


async def test_compute_diff_round_trip_via_stored_holdings(
    db_session: AsyncSession,
) -> None:
    """compute_diff loads ORM holdings, runs through the pure diff engine
    and surfaces NEW + EXITED rows correctly."""
    user = await _mk_user(db_session, "lf2@x.com", "lf2")
    filer = await _setup_subscribed_filer(db_session, user, cik="0007666666")

    filing_repo = F13FilingRepo(db_session)
    holding_repo = F13HoldingRepo(db_session)

    # Q3: holds AAPL only.
    q3 = await filing_repo.create(
        filer_id=filer.id, accession_number="q3", form_type="13F-HR",
        report_period_end=date(2025, 9, 30),
        filed_at=datetime(2025, 11, 1, tzinfo=UTC),
        total_value_usd=Decimal("1000000"),
        options_notional_usd=Decimal("0"),
        total_positions=1, raw_xml_url="x",
    )
    await holding_repo.bulk_insert(
        filing_id=q3.id,
        holdings=[{
            "cusip": "037833100",
            "name_of_issuer": "APPLE INC",
            "value_usd": Decimal("1000000"),
            "shares": Decimal("100"),
            "investment_discretion": "SOLE",
            "voting_authority_sole": Decimal("100"),
            "voting_authority_shared": Decimal("0"),
            "voting_authority_none": Decimal("0"),
        }],
    )
    # Q4: drops AAPL, picks up NVDA.
    q4 = await filing_repo.create(
        filer_id=filer.id, accession_number="q4", form_type="13F-HR",
        report_period_end=date(2025, 12, 31),
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("2000000"),
        options_notional_usd=Decimal("0"),
        total_positions=1, raw_xml_url="x",
    )
    await holding_repo.bulk_insert(
        filing_id=q4.id,
        holdings=[{
            "cusip": "67066G104",
            "name_of_issuer": "NVIDIA CORP",
            "value_usd": Decimal("2000000"),
            "shares": Decimal("50"),
            "investment_discretion": "SOLE",
            "voting_authority_sole": Decimal("50"),
            "voting_authority_shared": Decimal("0"),
            "voting_authority_none": Decimal("0"),
        }],
    )
    await db_session.commit()

    edgar = MockEdgarClient()
    svc = F13FilingService(db_session, user, edgar)
    prev, curr, changes = await svc.compute_diff(
        filer.id, date(2025, 9, 30), date(2025, 12, 31)
    )
    assert len(prev) == 1
    assert len(curr) == 1
    change_types = {c.change_type.value for c in changes}
    # AAPL EXITED, NVDA NEW
    assert change_types == {"EXITED", "NEW"}


# ═════════════════════════════════════════════════════════════════════════════
# F13CrossStockService (2 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_cross_stock_free_tier_blocked(
    db_session: AsyncSession,
) -> None:
    """FREE tier without institutional_ownership_panel feature → blocked."""
    user = await _mk_user(
        db_session, "cs1@x.com", "cs1", tier=UserTier.FREE
    )
    svc = F13CrossStockService(db_session, user)
    with patch(
        "app.services.institutional.cross_stock_service.settings"
    ) as s:
        s.enable_monetization = True
        with pytest.raises(F13TierFeatureUnavailable) as exc:
            await svc.get_institutional_holders_for_stock("AAPL")
        assert exc.value.feature == "institutional_ownership_panel"


async def test_cross_stock_pro_tier_returns_grouped_holders(
    db_session: AsyncSession,
) -> None:
    """PRO tier: returns one row per filer (latest period wins)."""
    user = await _mk_user(
        db_session, "cs2@x.com", "cs2", tier=UserTier.PRO
    )

    # Seed two filers each with a filing on AAPL stock.
    repo = F13FilerRepo(db_session)
    filer_a = await repo.create(cik="0008000001", name="Filer A")
    filer_b = await repo.create(cik="0008000002", name="Filer B")
    stock = Stock(symbol="AAPL", name="Apple", market=Market.US_NASDAQ)
    db_session.add(stock)
    await db_session.commit()
    await db_session.refresh(stock)

    filing_repo = F13FilingRepo(db_session)
    holding_repo = F13HoldingRepo(db_session)
    for f, period, shares, accession in [
        (filer_a, date(2025, 9, 30), Decimal("100"), "a-q3"),
        (filer_a, date(2025, 12, 31), Decimal("200"), "a-q4"),
        (filer_b, date(2025, 12, 31), Decimal("75"), "b-q4"),
    ]:
        filing = await filing_repo.create(
            filer_id=f.id, accession_number=accession, form_type="13F-HR",
            report_period_end=period,
            filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
            total_value_usd=Decimal("1"),
            options_notional_usd=Decimal("0"),
            total_positions=1,
            raw_xml_url="x",
        )
        await holding_repo.bulk_insert(
            filing_id=filing.id,
            holdings=[{
                "cusip": "037833100",
                "name_of_issuer": "APPLE INC",
                "value_usd": Decimal("1000"),
                "shares": shares,
                "investment_discretion": "SOLE",
                "voting_authority_sole": shares,
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
                "stock_id": stock.id,
            }],
        )
    await db_session.commit()

    svc = F13CrossStockService(db_session, user)
    rows = await svc.get_institutional_holders_for_stock("AAPL")

    # Expect one row per filer (most recent period each).
    by_filer = {r["filer_cik"]: r for r in rows}
    assert set(by_filer.keys()) == {"0008000001", "0008000002"}
    # Filer A's latest is Q4 (200 shares), not Q3 (100 shares).
    assert by_filer["0008000001"]["latest_shares"] == Decimal("200")
    assert by_filer["0008000001"]["latest_period_end"] == date(2025, 12, 31)


# ═════════════════════════════════════════════════════════════════════════════
# Audit log coverage (rolled into the cases above plus this final sweep)
# ═════════════════════════════════════════════════════════════════════════════


async def test_refresh_emits_audit_event(
    db_session: AsyncSession,
) -> None:
    """A successful refresh writes one f13_filer_refreshed audit row."""
    user = await _mk_user(db_session, "au1@x.com", "au1")
    filer = await _setup_subscribed_filer(db_session, user, cik="0009000001")

    edgar = MockEdgarClient()
    edgar.set_filings_response(
        "0009000001",
        [_mk_filing_meta("audit-acc", date(2025, 12, 31))],
    )

    svc = F13FilingService(db_session, user, edgar)
    await svc.refresh_filer(filer.id)
    await db_session.commit()

    assert (
        await _count_audit(db_session, "f13_filer_refreshed", user.id)
        == 1
    )


# Silence pyflakes for the asyncio import in case future tests grow into using it.
_ = asyncio
