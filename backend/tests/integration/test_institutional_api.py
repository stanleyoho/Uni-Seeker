"""Integration tests for /api/v1/institutional/* — 13F Holdings Tracker
Phase 1 Batch C.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5 + §8 + §13 AC matrix.

Layout (~22 cases):

  Filers (~13):
    subscribe happy / quota (free 2nd) / basic 5th passes / pro unlimited
    duplicate 409 / list / unsubscribe 204 / unsubscribe 404
    search local / search merges edgar / refresh happy / refresh concurrent 429
    refresh unknown filer 404

  Filings (~5):
    list filings paginated / get holdings latest / get holdings ISO date
    get diff / not subscribed 404

  Cross-stock (~3):
    Pro success / free feature 403 / unknown symbol empty

  Misc (~2):
    decimal-as-string serialization / mounted routes smoke

Tier guard: `enable_monetization` is False by default in `app.config`,
so dependency-layer `tier_guard` is a no-op. For the tier-block tests
we monkey-patch the FastAPI `app.dependency_overrides` for `require_auth`
to inject a user with the right tier, AND patch
`app.modules.billing.tier_limits.settings` so the guard actually
fires.

EdgarClient is dep-overridden to `_MockEdgarClient`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.institutional._deps import get_edgar_client
from app.auth import create_access_token
from app.db.models.institutional.subscription import F13UserSubscription
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
from app.services.institutional.filing_service import F13FilingService

# ── Helpers ─────────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    email: str,
    username: str | None = None,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=username or email.split("@")[0],
    )
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


def _client_app(client: AsyncClient):
    """Grab the FastAPI app instance the test client is bound to.

    `tests/conftest.py::client` calls `create_app()` which returns a
    NEW instance (not `app.main.app`), so we MUST override on this
    instance for dep overrides to actually fire.
    """
    return client._transport.app  # type: ignore[attr-defined]


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


class _MockEdgarClient:
    """Test double for `EdgarClient` — duck-typed.

    Implements the methods consumed by `F13FilerSearchService` and
    `F13FilingService`. State is set up via the `set_*_response`
    helpers; counters (`calls_*`) let tests assert mock interactions
    without pulling in `AsyncMock`.
    """

    def __init__(self) -> None:
        self._filings_responses: dict[str, list[FilingMetadata]] = {}
        self._xml_responses: dict[str, str] = {}
        self._search_response: list[FilerMetadata] = []
        self.calls_search: list[str] = []
        self.calls_list_filings: list[str] = []
        self.calls_fetch_xml: list[str] = []

    def set_filings_response(self, cik: str, filings: list[FilingMetadata]) -> None:
        self._filings_responses[cik] = list(filings)

    def set_xml_response(self, url: str, xml: str) -> None:
        self._xml_responses[url] = xml

    def set_search_response(self, hits: list[FilerMetadata]) -> None:
        self._search_response = list(hits)

    async def search_filers_by_name(self, name_query: str, limit: int = 20) -> list[FilerMetadata]:
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


@pytest.fixture
def mock_edgar(client: AsyncClient):
    """Override `get_edgar_client` with a `_MockEdgarClient` instance.

    Yields the mock so individual tests can configure responses /
    inspect counters.
    """
    app = _client_app(client)
    mock = _MockEdgarClient()
    app.dependency_overrides[get_edgar_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_edgar_client, None)


# ═════════════════════════════════════════════════════════════════════════════
# Filers — subscribe / list / unsubscribe / search / refresh
# ═════════════════════════════════════════════════════════════════════════════


async def test_subscribe_filer_201_creates_subscription(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """POST /institutional/filers → 201, persists row + subscription."""
    user = await _mk_user(db_session, "sub01@x.com", tier=UserTier.PRO)
    resp = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0001000001", "name": "Acme LP", "legal_name": "ACME LP"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filer"]["cik"] == "0001000001"
    assert body["filer"]["name"] == "Acme LP"
    assert body["notify_on_new_filing"] is True

    # subscription row exists
    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 1


async def test_subscribe_filer_free_tier_2nd_blocked(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """FREE.max_tracked_filers=1 → 2nd subscribe 403 limit_exceeded."""
    user = await _mk_user(db_session, "sub02@x.com", tier=UserTier.FREE)

    # First subscribe: should succeed regardless of monetisation toggle.
    first = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0001000002", "name": "Filer One"},
    )
    assert first.status_code == 201, first.text

    # Flip monetisation on for both the dep-layer guard AND the service
    # second line so the 2nd subscribe actually trips the limit.
    with (
        patch("app.modules.billing.tier_limits.settings") as guard_settings,
        patch("app.services.institutional.subscription_service.settings") as svc_settings,
    ):
        guard_settings.enable_monetization = True
        svc_settings.enable_monetization = True
        second = await client.post(
            "/api/v1/institutional/filers",
            headers=_auth(user),
            json={"cik": "0001000003", "name": "Filer Two"},
        )
    assert second.status_code == 403, second.text
    assert "limit_exceeded:max_tracked_filers" in second.json()["message"]


async def test_subscribe_filer_basic_tier_5th_passes(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """BASIC.max_tracked_filers=5 → 5 subscribes all succeed."""
    user = await _mk_user(db_session, "sub03@x.com", tier=UserTier.BASIC)
    for i in range(5):
        resp = await client.post(
            "/api/v1/institutional/filers",
            headers=_auth(user),
            json={"cik": f"000200000{i}", "name": f"Filer {i}"},
        )
        assert resp.status_code == 201, resp.text

    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 5


async def test_subscribe_filer_pro_tier_unlimited(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """PRO.max_tracked_filers=null → 10 subscribes ok."""
    user = await _mk_user(db_session, "sub04@x.com", tier=UserTier.PRO)
    with (
        patch("app.modules.billing.tier_limits.settings") as guard_settings,
        patch("app.services.institutional.subscription_service.settings") as svc_settings,
    ):
        guard_settings.enable_monetization = True
        svc_settings.enable_monetization = True
        for i in range(10):
            resp = await client.post(
                "/api/v1/institutional/filers",
                headers=_auth(user),
                json={"cik": f"000300000{i}", "name": f"Pro Filer {i}"},
            )
            assert resp.status_code == 201


async def test_subscribe_already_subscribed_409(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Re-subscribing to the same CIK → 409 f13_subscription_exists."""
    user = await _mk_user(db_session, "sub05@x.com", tier=UserTier.PRO)
    first = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0004000001", "name": "Dup Filer"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0004000001", "name": "Dup Filer"},
    )
    assert second.status_code == 409
    assert "f13_subscription_exists" in second.json()["message"]


async def test_list_subscriptions_returns_user_subscribed(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """GET /institutional/filers returns only user's subscriptions."""
    user_a = await _mk_user(db_session, "lis01a@x.com", tier=UserTier.PRO)
    user_b = await _mk_user(db_session, "lis01b@x.com", tier=UserTier.PRO)
    await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user_a),
        json={"cik": "0005000001", "name": "User A Filer"},
    )

    resp_a = await client.get("/api/v1/institutional/filers", headers=_auth(user_a))
    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["cik"] == "0005000001"

    resp_b = await client.get("/api/v1/institutional/filers", headers=_auth(user_b))
    assert resp_b.status_code == 200
    assert resp_b.json() == []


async def test_unsubscribe_204(client: AsyncClient, db_session: AsyncSession, mock_edgar) -> None:
    """DELETE /institutional/filers/{id} → 204 + removes row."""
    user = await _mk_user(db_session, "uns01@x.com", tier=UserTier.PRO)
    create_resp = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0006000001", "name": "Removable"},
    )
    filer_id = create_resp.json()["filer"]["id"]

    resp = await client.delete(
        f"/api/v1/institutional/filers/{filer_id}",
        headers=_auth(user),
    )
    assert resp.status_code == 204

    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 0


async def test_unsubscribe_unknown_filer_404(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """DELETE on a filer the user is not subscribed to → 404."""
    user = await _mk_user(db_session, "uns02@x.com", tier=UserTier.PRO)
    resp = await client.delete(
        "/api/v1/institutional/filers/9999999",
        headers=_auth(user),
    )
    assert resp.status_code == 404
    assert "f13_filer_not_found" in resp.json()["message"]


async def test_search_filers_local_only(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """POST /institutional/filers/search returns local hits."""
    user = await _mk_user(db_session, "srch01@x.com", tier=UserTier.PRO)
    await F13FilerRepo(db_session).create(cik="0007000001", name="Berkshire Hathaway")
    await db_session.commit()

    resp = await client.post(
        "/api/v1/institutional/filers/search?q=berkshire",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) >= 1
    assert rows[0]["is_locally_known"] is True
    assert rows[0]["cik"] == "0007000001"


async def test_search_filers_merges_edgar(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Local hit + EDGAR augmentation via the dep-overridden mock."""
    user = await _mk_user(db_session, "srch02@x.com", tier=UserTier.PRO)
    await F13FilerRepo(db_session).create(cik="0007000002", name="Renaissance Tech")
    await db_session.commit()
    mock_edgar.set_search_response(
        [
            FilerMetadata(
                cik="0007000999",
                name="Renaissance Partners",
                legal_name="RENAISSANCE PARTNERS LLC",
            ),
        ]
    )

    resp = await client.post(
        "/api/v1/institutional/filers/search?q=renaissance",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    ciks = {r["cik"] for r in rows}
    assert "0007000002" in ciks
    assert "0007000999" in ciks
    assert mock_edgar.calls_search == ["renaissance"]


async def test_refresh_filer_happy_path_200(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """POST /institutional/filers/{id}/refresh returns ingest counts."""
    user = await _mk_user(db_session, "rf01@x.com", tier=UserTier.PRO)
    create_resp = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0008000001", "name": "Refreshable LP"},
    )
    filer_id = create_resp.json()["filer"]["id"]
    F13FilingService._locks.pop(filer_id, None)

    mock_edgar.set_filings_response(
        "0008000001",
        [
            _mk_filing_meta(
                "acc-q4",
                date(2025, 12, 31),
                url="https://example.com/q4.xml",
            ),
        ],
    )
    mock_edgar.set_xml_response("https://example.com/q4.xml", _MINIMAL_INFOTABLE_XML)

    resp = await client.post(
        f"/api/v1/institutional/filers/{filer_id}/refresh",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filings_added"] == 1
    assert body["holdings_added"] == 2


async def test_refresh_filer_concurrent_429(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """If the per-filer lock is held, refresh returns 429."""
    user = await _mk_user(db_session, "rf02@x.com", tier=UserTier.PRO)
    create_resp = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0008000002", "name": "Locked LP"},
    )
    filer_id = create_resp.json()["filer"]["id"]

    # Pre-acquire the lock so the request hits the busy path.
    svc = F13FilingService(db_session, user, mock_edgar)  # type: ignore[arg-type]
    lock = await svc._get_lock(filer_id)
    await lock.acquire()
    try:
        resp = await client.post(
            f"/api/v1/institutional/filers/{filer_id}/refresh",
            headers=_auth(user),
        )
        assert resp.status_code == 429
        assert "f13_refresh_in_flight" in resp.json()["message"]
    finally:
        lock.release()
        F13FilingService._locks.pop(filer_id, None)


async def test_refresh_filer_unknown_404(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Refresh on a filer the user is not subscribed to → 404."""
    user = await _mk_user(db_session, "rf03@x.com", tier=UserTier.PRO)
    resp = await client.post(
        "/api/v1/institutional/filers/9999999/refresh",
        headers=_auth(user),
    )
    assert resp.status_code == 404
    assert "f13_filer_not_found" in resp.json()["message"]


# ═════════════════════════════════════════════════════════════════════════════
# Filings — list / holdings / diff
# ═════════════════════════════════════════════════════════════════════════════


async def _seed_filer_with_filings(
    db: AsyncSession, user: User, cik: str = "0010000001"
) -> tuple[int, list[int]]:
    """Helper: create filer + subscribe user + insert 2 filings each
    with 2 holdings. Returns (filer_id, [filing_id_q3, filing_id_q4])."""
    filer = await F13FilerRepo(db).create(cik=cik, name="Filing Holder")
    sub_repo = F13UserSubscriptionRepo(db)
    await sub_repo.subscribe(user_id=user.id, filer_id=filer.id)

    filing_repo = F13FilingRepo(db)
    holding_repo = F13HoldingRepo(db)
    filing_ids = []
    for period, accession, shares in [
        (date(2025, 9, 30), f"{cik[-3:]}-q3", Decimal("100")),
        (date(2025, 12, 31), f"{cik[-3:]}-q4", Decimal("200")),
    ]:
        filing = await filing_repo.create(
            filer_id=filer.id,
            accession_number=accession,
            form_type="13F-HR",
            report_period_end=period,
            filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
            total_value_usd=Decimal("1000000"),
            options_notional_usd=Decimal("0"),
            total_positions=1,
            raw_xml_url="https://example.com/x.xml",
        )
        await holding_repo.bulk_insert(
            filing_id=filing.id,
            holdings=[
                {
                    "cusip": "037833100",
                    "name_of_issuer": "APPLE INC",
                    "value_usd": Decimal("1000000"),
                    "shares": shares,
                    "investment_discretion": "SOLE",
                    "voting_authority_sole": shares,
                    "voting_authority_shared": Decimal("0"),
                    "voting_authority_none": Decimal("0"),
                }
            ],
        )
        filing_ids.append(filing.id)
    await db.commit()
    return filer.id, filing_ids


async def test_list_filings_paginated(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """GET /institutional/filers/{id}/filings returns DESC ordered list."""
    user = await _mk_user(db_session, "fl01@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user)

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/filings",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 2
    # newest first
    assert rows[0]["report_period_end"] == "2025-12-31"
    assert rows[1]["report_period_end"] == "2025-09-30"


async def test_get_holdings_latest(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """period=latest resolves to Q4 (most recent filing)."""
    user = await _mk_user(db_session, "fl02@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user, cik="0010000002")

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings?period=latest",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filing"]["report_period_end"] == "2025-12-31"
    assert len(body["holdings"]) == 1
    assert body["holdings"][0]["cusip"] == "037833100"


async def test_get_holdings_specific_period(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """period=2025-09-30 picks the Q3 filing."""
    user = await _mk_user(db_session, "fl03@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user, cik="0010000003")

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings?period=2025-09-30",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filing"]["report_period_end"] == "2025-09-30"


async def test_get_diff_returns_changes(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """GET /diff between two periods surfaces INCREASED row for AAPL."""
    user = await _mk_user(db_session, "fl04@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user, cik="0010000004")

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/diff",
        params={"from": "2025-09-30", "to": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prev_period"] == "2025-09-30"
    assert body["curr_period"] == "2025-12-31"
    change_types = {c["change_type"] for c in body["changes"]}
    assert "INCREASED" in change_types


async def test_get_filings_not_subscribed_404(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """User without subscription → 404 (no information leak)."""
    user_a = await _mk_user(db_session, "fl05a@x.com", tier=UserTier.PRO)
    user_b = await _mk_user(db_session, "fl05b@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user_a, cik="0010000005")

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/filings",
        headers=_auth(user_b),
    )
    assert resp.status_code == 404
    assert "f13_filer_not_found" in resp.json()["message"]


# ═════════════════════════════════════════════════════════════════════════════
# Cross-stock — /stocks/{symbol}/institutional
# ═════════════════════════════════════════════════════════════════════════════


async def _seed_cross_stock(
    db: AsyncSession, symbol: str = "AAPL", cusip: str = "037833100"
) -> int:
    """Seed a stock + two filers + holdings on this stock. Returns stock_id."""
    stock = Stock(symbol=symbol, name="Test Stock", market=Market.US_NASDAQ)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    repo = F13FilerRepo(db)
    filer_a = await repo.create(cik="0011000001", name="Filer Alpha")
    filer_b = await repo.create(cik="0011000002", name="Filer Beta")

    filing_repo = F13FilingRepo(db)
    holding_repo = F13HoldingRepo(db)
    for filer, accession, shares in [
        (filer_a, "x-a-q4", Decimal("100")),
        (filer_b, "x-b-q4", Decimal("50")),
    ]:
        filing = await filing_repo.create(
            filer_id=filer.id,
            accession_number=accession,
            form_type="13F-HR",
            report_period_end=date(2025, 12, 31),
            filed_at=datetime(2026, 2, 14, tzinfo=UTC),
            total_value_usd=Decimal("1000"),
            options_notional_usd=Decimal("0"),
            total_positions=1,
            raw_xml_url="x",
        )
        await holding_repo.bulk_insert(
            filing_id=filing.id,
            holdings=[
                {
                    "cusip": cusip,
                    "name_of_issuer": "Test Stock",
                    "value_usd": Decimal("1000"),
                    "shares": shares,
                    "investment_discretion": "SOLE",
                    "voting_authority_sole": shares,
                    "voting_authority_shared": Decimal("0"),
                    "voting_authority_none": Decimal("0"),
                    "stock_id": stock.id,
                }
            ],
        )
    await db.commit()
    return stock.id


async def test_institutional_for_stock_pro_tier(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """PRO user sees both filer rows on the stock."""
    user = await _mk_user(db_session, "cs01@x.com", tier=UserTier.PRO)
    stock_id = await _seed_cross_stock(db_session)

    resp = await client.get(
        "/api/v1/institutional/stocks/AAPL/institutional",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["stock_id"] == stock_id
    ciks = {h["filer_cik"] for h in body["holders"]}
    assert ciks == {"0011000001", "0011000002"}


async def test_institutional_for_stock_free_tier_403_feature(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """FREE user gets 403 feature_unavailable when monetisation on."""
    user = await _mk_user(db_session, "cs02@x.com", tier=UserTier.FREE)
    await _seed_cross_stock(db_session, symbol="AAPL2", cusip="111111111")

    with patch("app.services.institutional.cross_stock_service.settings") as svc_settings:
        svc_settings.enable_monetization = True
        resp = await client.get(
            "/api/v1/institutional/stocks/AAPL2/institutional",
            headers=_auth(user),
        )
    assert resp.status_code == 403
    assert "feature_unavailable:institutional_ownership_panel" in resp.json()["message"]


async def test_institutional_for_stock_unknown_symbol_empty(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Unknown symbol → 200 with empty holders + stock_id null."""
    user = await _mk_user(db_session, "cs03@x.com", tier=UserTier.PRO)
    resp = await client.get(
        "/api/v1/institutional/stocks/NOPE/institutional",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NOPE"
    assert body["stock_id"] is None
    assert body["holders"] == []


# ═════════════════════════════════════════════════════════════════════════════
# Misc — Decimal-as-string + route mount smoke
# ═════════════════════════════════════════════════════════════════════════════


async def test_decimal_as_string_serialization(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Numeric fields render as JSON strings (CLAUDE.md Decimal-as-string)."""
    user = await _mk_user(db_session, "dec01@x.com", tier=UserTier.PRO)
    filer_id, _ = await _seed_filer_with_filings(db_session, user, cik="0012000001")

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings?period=latest",
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    holding = body["holdings"][0]
    assert isinstance(holding["value_usd"], str)
    assert isinstance(holding["shares"], str)
    # Decimal serializer keeps the exact form (no scientific notation).
    # The Numeric(24, 2) column drives a "1000000.00" canonical form.
    assert "e" not in holding["value_usd"].lower()
    assert Decimal(holding["value_usd"]) == Decimal("1000000")


async def test_app_imports_institutional_routes_mounted(
    client: AsyncClient,
) -> None:
    """Smoke: GET /api/openapi.json exposes the new institutional paths."""
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    # Spot-check each sub-router emitted something.
    assert "/api/v1/institutional/filers" in paths
    assert "/api/v1/institutional/filers/{filer_id}" in paths
    assert "/api/v1/institutional/filers/{filer_id}/filings" in paths
    assert "/api/v1/institutional/filers/{filer_id}/holdings" in paths
    assert "/api/v1/institutional/filers/{filer_id}/diff" in paths
    assert "/api/v1/institutional/filers/{filer_id}/refresh" in paths
    assert "/api/v1/institutional/stocks/{symbol}/institutional" in paths
    # Legacy FinMind endpoint preserved.
    assert "/api/v1/institutional/{symbol}" in paths
