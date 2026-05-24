"""Integration tests for /api/v1/institutional/filers/{id}/holdings/{identifier}/history.

Spec: Round 12 — Position history endpoint. Replaces the frontend's
N parallel useHoldings fetches in `holdings-timeline.tsx` with a
single round trip.

Layout (~12 cases):
  - happy path: 4 filings, all hold AAPL, monotonic increasing → INCREASED chain
  - mix: hold Q1 / Q2 increase / Q3 decrease / Q4 exit
  - never held: filer has filings but none of them hold this stock
  - cross-quarter NEW: first filing didn't hold, second filing does
  - pagination via `limit` (limit=2 with 4 filings → 2 newest entries)
  - date range filter narrows window
  - tier check / Pro bypass: free user without subscription + Pro feature
    bypass disabled → 404
  - Pro user bypass subscription: Pro + feature on + no subscription → 200
  - cross-user (user not subscribed to filer, FREE tier) → 404
  - by symbol match (uses stocks.symbol JOIN)
  - by cusip match (no stock row)
  - Decimal-as-string serialization

EdgarClient is dep-overridden to a no-op stub via the `mock_edgar`
fixture — this endpoint does not call EDGAR, but the API layer still
constructs the service with one.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest  # noqa: F401  (pytest fixtures resolved by name)
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.institutional._deps import get_edgar_client
from app.auth import create_access_token
from app.models.enums import Market, UserTier
from app.models.stock import Stock
from app.models.user import User
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
    F13UserSubscriptionRepo,
)

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
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.email)}"
    }


def _client_app(client: AsyncClient):
    return client._transport.app  # type: ignore[attr-defined]


class _NoopEdgarClient:
    """Minimal duck-type — history endpoint never calls EDGAR but the
    service constructor still expects an edgar client."""


@pytest.fixture
def mock_edgar(client: AsyncClient):
    app = _client_app(client)
    mock = _NoopEdgarClient()
    app.dependency_overrides[get_edgar_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_edgar_client, None)


async def _seed_filer(
    db: AsyncSession, user: User, cik: str = "0020000001", subscribe: bool = True
) -> int:
    """Create a filer + (optionally) subscribe the user. Returns filer_id."""
    filer = await F13FilerRepo(db).create(cik=cik, name=f"Filer {cik[-3:]}")
    if subscribe:
        await F13UserSubscriptionRepo(db).subscribe(
            user_id=user.id, filer_id=filer.id
        )
    await db.commit()
    return filer.id


async def _insert_filing(
    db: AsyncSession,
    *,
    filer_id: int,
    period: date,
    accession: str,
    form_type: str = "13F-HR",
    holdings: list[dict] | None = None,
) -> int:
    """Insert a filing + holdings. Returns filing_id."""
    filing = await F13FilingRepo(db).create(
        filer_id=filer_id,
        accession_number=accession,
        form_type=form_type,
        report_period_end=period,
        filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
        total_value_usd=Decimal("1000000"),
        options_notional_usd=Decimal("0"),
        total_positions=len(holdings or []),
        raw_xml_url="https://example.com/x.xml",
    )
    if holdings:
        await F13HoldingRepo(db).bulk_insert(
            filing_id=filing.id, holdings=holdings
        )
    return filing.id


def _aapl(shares: Decimal, stock_id: int | None = None) -> dict:
    return {
        "cusip": "037833100",
        "name_of_issuer": "APPLE INC",
        "value_usd": shares * Decimal("100"),
        "shares": shares,
        "investment_discretion": "SOLE",
        "voting_authority_sole": shares,
        "voting_authority_shared": Decimal("0"),
        "voting_authority_none": Decimal("0"),
        "stock_id": stock_id,
    }


def _other(cusip: str, name: str = "OTHER CORP") -> dict:
    return {
        "cusip": cusip,
        "name_of_issuer": name,
        "value_usd": Decimal("10000"),
        "shares": Decimal("100"),
        "investment_discretion": "SOLE",
        "voting_authority_sole": Decimal("100"),
        "voting_authority_shared": Decimal("0"),
        "voting_authority_none": Decimal("0"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Happy path tests
# ═════════════════════════════════════════════════════════════════════════════


async def test_history_monotonic_increasing_4_quarters(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """4 filings, all hold AAPL, increasing shares → 3 INCREASED + 1 NEW."""
    user = await _mk_user(db_session, "h01@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000001")

    periods = [
        (date(2025, 3, 31), "acc-q1", Decimal("100")),
        (date(2025, 6, 30), "acc-q2", Decimal("200")),
        (date(2025, 9, 30), "acc-q3", Decimal("300")),
        (date(2025, 12, 31), "acc-q4", Decimal("400")),
    ]
    for period, acc, shares in periods:
        await _insert_filing(
            db_session,
            filer_id=filer_id,
            period=period,
            accession=acc,
            holdings=[_aapl(shares)],
        )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filer_id"] == filer_id
    assert body["cusip"] == "037833100"
    assert len(body["entries"]) == 4
    # Sorted ASC by period.
    assert body["entries"][0]["report_period_end"] == "2025-03-31"
    assert body["entries"][-1]["report_period_end"] == "2025-12-31"
    # First entry is NEW (no prior baseline).
    assert body["entries"][0]["change_type"] == "NEW"
    # Subsequent: INCREASED.
    for entry in body["entries"][1:]:
        assert entry["change_type"] == "INCREASED"
    # delta_shares on Q2 = 200 - 100 = 100.
    assert Decimal(body["entries"][1]["delta_shares"]) == Decimal("100")
    # delta_pct on Q2 = 100/100 = 100%.
    assert Decimal(body["entries"][1]["delta_pct"]) == Decimal("100")


async def test_history_mix_classifications(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Q1 hold / Q2 increase / Q3 decrease / Q4 exit → NEW, INCREASED, DECREASED, EXITED."""
    user = await _mk_user(db_session, "h02@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000002")

    # Q1 — initial position
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 3, 31),
        accession="acc-mix-q1",
        holdings=[_aapl(Decimal("100"))],
    )
    # Q2 — increase
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 6, 30),
        accession="acc-mix-q2",
        holdings=[_aapl(Decimal("250"))],
    )
    # Q3 — decrease
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 9, 30),
        accession="acc-mix-q3",
        holdings=[_aapl(Decimal("80"))],
    )
    # Q4 — exited (filed but no AAPL row)
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="acc-mix-q4",
        holdings=[_other("999999999")],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    types = [e["change_type"] for e in resp.json()["entries"]]
    assert types == ["NEW", "INCREASED", "DECREASED", "EXITED"]


async def test_history_never_held(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Filer filed 2 quarters but never held AAPL → both entries NOT_HELD."""
    user = await _mk_user(db_session, "h03@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000003")

    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 9, 30),
        accession="acc-nv-q3",
        holdings=[_other("111111111")],
    )
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="acc-nv-q4",
        holdings=[_other("222222222")],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cusip"] is None  # never appeared in any filing
    assert body["symbol"] is None
    assert len(body["entries"]) == 2
    assert all(e["change_type"] == "NOT_HELD" for e in body["entries"])
    assert all(e["shares"] is None for e in body["entries"])


async def test_history_cross_quarter_new(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """First filing didn't hold AAPL, second filing does → NOT_HELD then NEW."""
    user = await _mk_user(db_session, "h04@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000004")

    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 9, 30),
        accession="acc-new-q3",
        holdings=[_other("888888888")],
    )
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="acc-new-q4",
        holdings=[_aapl(Decimal("500"))],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert [e["change_type"] for e in entries] == ["NOT_HELD", "NEW"]
    assert entries[0]["shares"] is None
    assert Decimal(entries[1]["shares"]) == Decimal("500")


# ═════════════════════════════════════════════════════════════════════════════
# Pagination / window tests
# ═════════════════════════════════════════════════════════════════════════════


async def test_history_limit_pagination(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """limit=2 with 4 filings → 2 newest entries returned, still ASC."""
    user = await _mk_user(db_session, "h05@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000005")

    for period, acc, shares in [
        (date(2025, 3, 31), "p-q1", Decimal("100")),
        (date(2025, 6, 30), "p-q2", Decimal("200")),
        (date(2025, 9, 30), "p-q3", Decimal("300")),
        (date(2025, 12, 31), "p-q4", Decimal("400")),
    ]:
        await _insert_filing(
            db_session,
            filer_id=filer_id,
            period=period,
            accession=acc,
            holdings=[_aapl(shares)],
        )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31", "limit": 2},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert len(entries) == 2
    # Newest 2 (Q3 + Q4) — repo picks newest, service re-sorts ASC.
    assert entries[0]["report_period_end"] == "2025-09-30"
    assert entries[1]["report_period_end"] == "2025-12-31"


async def test_history_date_range_filter(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """from_date/to_date narrows the window."""
    user = await _mk_user(db_session, "h06@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000006")

    for period, acc, shares in [
        (date(2024, 12, 31), "w-q0", Decimal("50")),  # before window
        (date(2025, 3, 31), "w-q1", Decimal("100")),
        (date(2025, 6, 30), "w-q2", Decimal("200")),
        (date(2025, 12, 31), "w-q4", Decimal("400")),  # after window
    ]:
        await _insert_filing(
            db_session,
            filer_id=filer_id,
            period=period,
            accession=acc,
            holdings=[_aapl(shares)],
        )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-09-30"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert [e["report_period_end"] for e in entries] == [
        "2025-03-31",
        "2025-06-30",
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Access control tests
# ═════════════════════════════════════════════════════════════════════════════


async def test_history_cross_user_not_subscribed_404(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """FREE user who doesn't own the subscription → 404, no info leak."""
    user_a = await _mk_user(db_session, "h07a@x.com", tier=UserTier.PRO)
    # FREE tier does NOT have institutional_ownership_panel feature.
    user_b = await _mk_user(db_session, "h07b@x.com", tier=UserTier.FREE)
    filer_id = await _seed_filer(db_session, user_a, cik="0020000007")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="x-q4",
        holdings=[_aapl(Decimal("100"))],
    )
    await db_session.commit()

    # Flip monetization on so the Pro bypass actually checks the flag.
    with patch(
        "app.services.institutional.filing_service.settings"
    ) as svc_settings:
        svc_settings.enable_monetization = True
        resp = await client.get(
            f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
            headers=_auth(user_b),
        )
    assert resp.status_code == 404
    assert "f13_filer_not_found" in resp.json()["message"]


async def test_history_pro_user_bypass_subscription(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """PRO user without subscription can read history (Pro feature bypass)."""
    owner = await _mk_user(db_session, "h08a@x.com", tier=UserTier.PRO)
    pro_other = await _mk_user(db_session, "h08b@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, owner, cik="0020000008")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="bp-q4",
        holdings=[_aapl(Decimal("700"))],
    )
    await db_session.commit()

    with patch(
        "app.services.institutional.filing_service.settings"
    ) as svc_settings:
        svc_settings.enable_monetization = True
        resp = await client.get(
            f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
            params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
            headers=_auth(pro_other),
        )
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert Decimal(entries[0]["shares"]) == Decimal("700")


async def test_history_monetization_off_subscription_only(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """With monetization OFF (default), only subscription gates access.

    A FREE user without a subscription still hits the Pro-bypass path
    because `enable_monetization=False` short-circuits the feature
    check. This is the dev/test parity behaviour and is intentional —
    matches the rest of the institutional services. The filer however
    must exist, otherwise the inner `_require_filer` still 404s.
    """
    user_owner = await _mk_user(db_session, "h09a@x.com", tier=UserTier.PRO)
    user_free = await _mk_user(db_session, "h09b@x.com", tier=UserTier.FREE)
    filer_id = await _seed_filer(db_session, user_owner, cik="0020000009")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="mon-q4",
        holdings=[_aapl(Decimal("100"))],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user_free),
    )
    # Monetization off → bypass kicks in regardless of tier.
    assert resp.status_code == 200, resp.text


# ═════════════════════════════════════════════════════════════════════════════
# Identifier matching tests
# ═════════════════════════════════════════════════════════════════════════════


async def test_history_by_symbol_resolves_via_stock_join(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Identifier=AAPL (symbol) → matches via stocks JOIN on holding.stock_id."""
    user = await _mk_user(db_session, "h10@x.com", tier=UserTier.PRO)
    # Create the Stock row first.
    stock = Stock(symbol="AAPL", name="Apple Inc", market=Market.US_NASDAQ)
    db_session.add(stock)
    await db_session.commit()
    await db_session.refresh(stock)

    filer_id = await _seed_filer(db_session, user, cik="0020000010")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 9, 30),
        accession="sym-q3",
        holdings=[_aapl(Decimal("100"), stock_id=stock.id)],
    )
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="sym-q4",
        holdings=[_aapl(Decimal("250"), stock_id=stock.id)],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/AAPL/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["cusip"] == "037833100"  # surfaced from the holding row
    entries = body["entries"]
    assert len(entries) == 2
    assert entries[0]["change_type"] == "NEW"
    assert entries[1]["change_type"] == "INCREASED"


async def test_history_by_cusip_without_stock_row(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """CUSIP-only path: no `stocks` row exists, holding has stock_id=None."""
    user = await _mk_user(db_session, "h11@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000011")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="cu-q4",
        holdings=[_aapl(Decimal("999"))],  # no stock_id mapping
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cusip"] == "037833100"
    assert body["symbol"] is None  # no stock row to resolve
    assert len(body["entries"]) == 1


# ═════════════════════════════════════════════════════════════════════════════
# Misc — serialization smoke
# ═════════════════════════════════════════════════════════════════════════════


async def test_history_decimal_as_string(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Numeric fields serialize as JSON strings (CLAUDE.md Decimal-as-string)."""
    user = await _mk_user(db_session, "h12@x.com", tier=UserTier.PRO)
    filer_id = await _seed_filer(db_session, user, cik="0020000012")
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 9, 30),
        accession="dec-q3",
        holdings=[_aapl(Decimal("100"))],
    )
    await _insert_filing(
        db_session,
        filer_id=filer_id,
        period=date(2025, 12, 31),
        accession="dec-q4",
        holdings=[_aapl(Decimal("250"))],
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/institutional/filers/{filer_id}/holdings/037833100/history",
        params={"from_date": "2025-01-01", "to_date": "2025-12-31"},
        headers=_auth(user),
    )
    assert resp.status_code == 200, resp.text
    entries = resp.json()["entries"]
    # All numeric fields are strings (or null).
    for e in entries:
        assert e["shares"] is None or isinstance(e["shares"], str)
        assert e["value_usd"] is None or isinstance(e["value_usd"], str)
    # The Q2 delta is 150 (250 - 100), serialized as a string.
    assert entries[1]["delta_shares"] == "150"
    # Pct is 150% as Decimal string.
    assert "150" in entries[1]["delta_pct"]
