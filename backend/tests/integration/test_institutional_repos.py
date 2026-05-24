"""Integration tests for institutional 13F repositories (Phase 1 / UNI-F13-001 Batch B1).

Layout per task brief:
    Filer        : 5 cases  (create / get_by_cik / search / get_or_create idempotent / update_latest_aum)
    Subscription : 6 cases  (subscribe / unsubscribe / list_by_user / count_by_user / is_subscribed / cross-user)
    Filing       : 5 cases  (create / unique constraint / list ordered DESC / latest / exists idempotency)
    Holding      : 4 cases  (bulk_insert / list_by_filing / list_by_stock JOIN / list_by_cusip)

All tests run against the shared `db_session` fixture (in-memory SQLite).
Each test seeds its own users + filers to verify isolation: a second
user must not see/mutate the first user's subscription rows, even
though `f13_filers` is a shared resource (Q2 decision).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.institutional.filing import F13Filing
from app.models.enums import Market, UserTier
from app.models.stock import Stock
from app.models.user import User
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
    F13UserSubscriptionRepo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.institutional.filer import F13Filer


# ── Shared helpers ──────────────────────────────────────────────────────────


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
    cik: str = "0001234567",
    name: str = "Test Fund LP",
) -> F13Filer:
    repo = F13FilerRepo(db)
    f = await repo.create(cik=cik, name=name)
    await db.commit()
    return f


async def _mk_filing(
    db: AsyncSession,
    filer_id: int,
    accession: str = "0001234567-25-000001",
    period: date = date(2025, 12, 31),
    form_type: str = "13F-HR",
    total_value_usd: Decimal = Decimal("100000000"),
    options_notional_usd: Decimal = Decimal("0"),
    total_positions: int = 10,
) -> F13Filing:
    repo = F13FilingRepo(db)
    f = await repo.create(
        filer_id=filer_id,
        accession_number=accession,
        form_type=form_type,
        report_period_end=period,
        filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
        total_value_usd=total_value_usd,
        options_notional_usd=options_notional_usd,
        total_positions=total_positions,
        raw_xml_url=f"https://www.sec.gov/Archives/edgar/data/x/{accession}/infotable.xml",
    )
    await db.commit()
    return f


# ═════════════════════════════════════════════════════════════════════════════
# F13FilerRepo (5 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_filer_repo_create_and_get_by_cik(
    db_session: AsyncSession,
) -> None:
    """Create returns a row with assigned id; get_by_cik echoes it back."""
    repo = F13FilerRepo(db_session)
    f = await repo.create(cik="0001234567", name="Acme Capital", legal_name="ACME CAPITAL LP")
    await db_session.commit()

    assert f.id is not None
    assert f.cik == "0001234567"
    assert f.legal_name == "ACME CAPITAL LP"

    got = await repo.get_by_cik("0001234567")
    assert got is not None
    assert got.id == f.id
    assert got.name == "Acme Capital"


async def test_filer_repo_search_by_name_substring(
    db_session: AsyncSession,
) -> None:
    """ILIKE %q% should match prefix / suffix / mid substrings."""
    repo = F13FilerRepo(db_session)
    for cik, name in [
        ("0000000001", "Berkshire Hathaway"),
        ("0000000002", "Berkshire Capital"),
        ("0000000003", "ARK Invest"),
    ]:
        await repo.create(cik=cik, name=name)
    await db_session.commit()

    hits = await repo.search_by_name("berkshire")
    assert {h.name for h in hits} == {
        "Berkshire Hathaway",
        "Berkshire Capital",
    }
    assert await repo.search_by_name("") == []
    assert await repo.search_by_name("nomatch") == []


async def test_filer_repo_get_or_create_idempotent(
    db_session: AsyncSession,
) -> None:
    """First call creates; second call returns same row, was_created=False."""
    repo = F13FilerRepo(db_session)
    first, created1 = await repo.get_or_create_by_cik(cik="0001111111", name="Fund A")
    await db_session.commit()
    assert created1 is True
    assert first.cik == "0001111111"

    second, created2 = await repo.get_or_create_by_cik(
        cik="0001111111", name="Fund A (different name)"
    )
    await db_session.commit()
    assert created2 is False
    assert second.id == first.id
    # We do NOT overwrite the name on subsequent get_or_create — Q2 decision.
    assert second.name == "Fund A"


async def test_filer_repo_update_latest_aum(
    db_session: AsyncSession,
) -> None:
    """update_latest_aum mutates the denormalised latest_* columns."""
    repo = F13FilerRepo(db_session)
    f = await repo.create(cik="0002222222", name="Bumpy LP")
    await db_session.commit()

    await repo.update_latest_aum(
        f.id,
        total_value_usd=Decimal("5500000000"),
        options_notional_usd=Decimal("13670000000"),
        position_count=42,
        filing_date=date(2025, 12, 31),
    )
    await db_session.commit()

    fresh = await repo.get_by_id(f.id)
    assert fresh is not None
    assert fresh.latest_total_value_usd == Decimal("5500000000")
    assert fresh.latest_options_notional_usd == Decimal("13670000000")
    assert fresh.latest_position_count == 42
    assert fresh.latest_filing_date == date(2025, 12, 31)


async def test_filer_repo_unique_cik_enforced(
    db_session: AsyncSession,
) -> None:
    """DB UNIQUE on cik rejects a duplicate raw insert."""
    repo = F13FilerRepo(db_session)
    await repo.create(cik="0003333333", name="One")
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(cik="0003333333", name="Two")
        await db_session.commit()
    # Important: leave the session in a clean state for the next test.
    await db_session.rollback()


# ═════════════════════════════════════════════════════════════════════════════
# F13UserSubscriptionRepo (6 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_subscription_repo_subscribe_and_is_subscribed(
    db_session: AsyncSession,
) -> None:
    """subscribe + is_subscribed round-trip."""
    user = await _mk_user(db_session, "su1@x.com", "su1")
    filer = await _mk_filer(db_session, cik="0001000001")
    repo = F13UserSubscriptionRepo(db_session)

    sub = await repo.subscribe(user_id=user.id, filer_id=filer.id)
    await db_session.commit()

    assert sub.id is not None
    assert sub.user_id == user.id
    assert sub.filer_id == filer.id
    assert await repo.is_subscribed(user.id, filer.id) is True
    assert await repo.is_subscribed(user.id, filer.id + 999) is False


async def test_subscription_repo_unsubscribe(
    db_session: AsyncSession,
) -> None:
    """unsubscribe returns True on hit, False on miss."""
    user = await _mk_user(db_session, "su2@x.com", "su2")
    filer = await _mk_filer(db_session, cik="0001000002")
    repo = F13UserSubscriptionRepo(db_session)

    await repo.subscribe(user_id=user.id, filer_id=filer.id)
    await db_session.commit()

    deleted = await repo.unsubscribe(user_id=user.id, filer_id=filer.id)
    await db_session.commit()
    assert deleted is True

    miss = await repo.unsubscribe(user_id=user.id, filer_id=filer.id)
    assert miss is False


async def test_subscription_repo_list_by_user_eager_loads_filer(
    db_session: AsyncSession,
) -> None:
    """list_by_user returns subscriptions with `filer` accessible without
    triggering an N+1 lazy-load expiration after a refresh."""
    user = await _mk_user(db_session, "su3@x.com", "su3")
    f1 = await _mk_filer(db_session, cik="0001000003", name="A")
    f2 = await _mk_filer(db_session, cik="0001000004", name="B")
    repo = F13UserSubscriptionRepo(db_session)

    await repo.subscribe(user_id=user.id, filer_id=f1.id)
    await repo.subscribe(user_id=user.id, filer_id=f2.id)
    await db_session.commit()

    rows = await repo.list_by_user(user.id)
    assert len(rows) == 2
    # Eager-loaded relationship — `filer.name` must not raise from a
    # detached session because selectinload pre-populated the attr.
    names = {r.filer.name for r in rows}
    assert names == {"A", "B"}


async def test_subscription_repo_list_filers_by_user(
    db_session: AsyncSession,
) -> None:
    """Convenience JOIN returns F13Filer rows, ordered by name ASC."""
    user = await _mk_user(db_session, "su4@x.com", "su4")
    f_z = await _mk_filer(db_session, cik="0001000005", name="Z fund")
    f_a = await _mk_filer(db_session, cik="0001000006", name="A fund")
    repo = F13UserSubscriptionRepo(db_session)
    await repo.subscribe(user_id=user.id, filer_id=f_z.id)
    await repo.subscribe(user_id=user.id, filer_id=f_a.id)
    await db_session.commit()

    filers = await repo.list_filers_by_user(user.id)
    assert [f.name for f in filers] == ["A fund", "Z fund"]


async def test_subscription_repo_count_by_user(
    db_session: AsyncSession,
) -> None:
    """count_by_user accurately reports tier-quota input."""
    user = await _mk_user(db_session, "su5@x.com", "su5")
    repo = F13UserSubscriptionRepo(db_session)
    assert await repo.count_by_user(user.id) == 0

    for n in range(3):
        f = await _mk_filer(db_session, cik=f"000100007{n}", name=f"F{n}")
        await repo.subscribe(user_id=user.id, filer_id=f.id)
    await db_session.commit()
    assert await repo.count_by_user(user.id) == 3


async def test_subscription_repo_user_isolation(
    db_session: AsyncSession,
) -> None:
    """User B must NEVER see A's subscriptions even when both share
    the (shared) filer row. The 3-attack pattern:
    (1) list isolation, (2) is_subscribed isolation, (3) unsubscribe
    isolation."""
    user_a = await _mk_user(db_session, "sua@x.com", "sua")
    user_b = await _mk_user(db_session, "sub@x.com", "sub")
    filer = await _mk_filer(db_session, cik="0001000099", name="Shared")
    repo = F13UserSubscriptionRepo(db_session)

    await repo.subscribe(user_id=user_a.id, filer_id=filer.id)
    await db_session.commit()

    # Attack 1: B's list_by_user is empty even though the filer exists.
    assert await repo.list_by_user(user_b.id) == []
    assert await repo.list_filers_by_user(user_b.id) == []

    # Attack 2: B's is_subscribed against A's filer returns False.
    assert await repo.is_subscribed(user_b.id, filer.id) is False
    assert await repo.is_subscribed(user_a.id, filer.id) is True

    # Attack 3: B's unsubscribe is a no-op; A's row survives.
    res = await repo.unsubscribe(user_id=user_b.id, filer_id=filer.id)
    assert res is False
    assert await repo.is_subscribed(user_a.id, filer.id) is True

    # count separates correctly
    assert await repo.count_by_user(user_a.id) == 1
    assert await repo.count_by_user(user_b.id) == 0


# ═════════════════════════════════════════════════════════════════════════════
# F13FilingRepo (5 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_filing_repo_create_and_get(db_session: AsyncSession) -> None:
    filer = await _mk_filer(db_session, cik="0002000001")
    repo = F13FilingRepo(db_session)
    f = await repo.create(
        filer_id=filer.id,
        accession_number="0002-25-000001",
        form_type="13F-HR",
        report_period_end=date(2025, 12, 31),
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("1000000"),
        options_notional_usd=Decimal("500000"),
        total_positions=30,
        raw_xml_url="https://example.com/xml",
    )
    await db_session.commit()

    got = await repo.get_by_id(f.id)
    assert got is not None
    assert got.form_type == "13F-HR"
    assert got.total_positions == 30


async def test_filing_repo_unique_filer_accession(
    db_session: AsyncSession,
) -> None:
    """UNIQUE (filer_id, accession_number) rejects duplicate refresh."""
    filer = await _mk_filer(db_session, cik="0002000002")
    repo = F13FilingRepo(db_session)
    await repo.create(
        filer_id=filer.id,
        accession_number="dup-acc",
        form_type="13F-HR",
        report_period_end=date(2025, 12, 31),
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("1"),
        options_notional_usd=Decimal("0"),
        total_positions=1,
        raw_xml_url="x",
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(
            filer_id=filer.id,
            accession_number="dup-acc",
            form_type="13F-HR",
            report_period_end=date(2025, 12, 31),
            filed_at=datetime(2026, 2, 14, tzinfo=UTC),
            total_value_usd=Decimal("1"),
            options_notional_usd=Decimal("0"),
            total_positions=1,
            raw_xml_url="x",
        )
        await db_session.commit()
    await db_session.rollback()


async def test_filing_repo_list_by_filer_orders_desc(
    db_session: AsyncSession,
) -> None:
    filer = await _mk_filer(db_session, cik="0002000003")
    for i, p in enumerate([date(2024, 12, 31), date(2025, 3, 31), date(2025, 12, 31)]):
        await _mk_filing(
            db_session,
            filer.id,
            accession=f"acc-{i}",
            period=p,
        )

    repo = F13FilingRepo(db_session)
    rows = await repo.list_by_filer(filer.id)
    assert [r.report_period_end for r in rows] == [
        date(2025, 12, 31),
        date(2025, 3, 31),
        date(2024, 12, 31),
    ]


async def test_filing_repo_get_latest_and_at_period(
    db_session: AsyncSession,
) -> None:
    filer = await _mk_filer(db_session, cik="0002000004")
    await _mk_filing(db_session, filer.id, accession="a1", period=date(2024, 12, 31))
    await _mk_filing(db_session, filer.id, accession="a2", period=date(2025, 12, 31))

    repo = F13FilingRepo(db_session)
    latest = await repo.get_latest_for_filer(filer.id)
    assert latest is not None
    assert latest.report_period_end == date(2025, 12, 31)

    exact = await repo.get_at_period(filer.id, date(2024, 12, 31))
    assert exact is not None
    assert exact.accession_number == "a1"

    missing = await repo.get_at_period(filer.id, date(2023, 9, 30))
    assert missing is None


async def test_filing_repo_exists_idempotency(
    db_session: AsyncSession,
) -> None:
    """`exists` is the cheap probe used by refresh to skip seen filings."""
    filer = await _mk_filer(db_session, cik="0002000005")
    repo = F13FilingRepo(db_session)
    await _mk_filing(
        db_session,
        filer.id,
        accession="exists-acc",
    )

    assert await repo.exists(filer.id, "exists-acc") is True
    assert await repo.exists(filer.id, "nope") is False
    assert await repo.exists(filer.id + 999, "exists-acc") is False


# ═════════════════════════════════════════════════════════════════════════════
# F13HoldingRepo (4 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_holding_repo_bulk_insert_and_list(
    db_session: AsyncSession,
) -> None:
    filer = await _mk_filer(db_session, cik="0003000001")
    filing = await _mk_filing(db_session, filer.id, accession="hbi-acc")
    repo = F13HoldingRepo(db_session)

    inserted = await repo.bulk_insert(
        filing_id=filing.id,
        holdings=[
            {
                "cusip": "037833100",  # AAPL
                "name_of_issuer": "APPLE INC",
                "value_usd": Decimal("1000000"),
                "shares": Decimal("5000"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("5000"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
            },
            {
                "cusip": "67066G104",  # NVDA
                "name_of_issuer": "NVIDIA CORP",
                "value_usd": Decimal("2000000"),
                "shares": Decimal("3000"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("3000"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
            },
        ],
    )
    await db_session.commit()
    assert inserted == 2

    rows = await repo.list_by_filing(filing.id)
    assert len(rows) == 2
    assert {r.cusip for r in rows} == {"037833100", "67066G104"}
    # Empty list does not raise and returns 0.
    assert await repo.bulk_insert(filing_id=filing.id, holdings=[]) == 0


async def test_holding_repo_list_by_filer_at_period_picks_amendment(
    db_session: AsyncSession,
) -> None:
    """When 13F-HR + 13F-HR/A exist for same period, amendment wins
    (most recent filed_at). Holdings returned reflect the amendment."""
    filer = await _mk_filer(db_session, cik="0003000002")
    period = date(2025, 12, 31)

    # Original 13F-HR filed early
    original = await F13FilingRepo(db_session).create(
        filer_id=filer.id,
        accession_number="orig-acc",
        form_type="13F-HR",
        report_period_end=period,
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("100"),
        options_notional_usd=Decimal("0"),
        total_positions=1,
        raw_xml_url="x",
    )
    # Amendment filed later
    amendment = await F13FilingRepo(db_session).create(
        filer_id=filer.id,
        accession_number="amend-acc",
        form_type="13F-HR/A",
        report_period_end=period,
        filed_at=datetime(2026, 4, 1, tzinfo=UTC),
        total_value_usd=Decimal("200"),
        options_notional_usd=Decimal("0"),
        total_positions=1,
        raw_xml_url="x2",
    )
    await db_session.commit()

    holding_repo = F13HoldingRepo(db_session)
    await holding_repo.bulk_insert(
        filing_id=original.id,
        holdings=[
            {
                "cusip": "111111111",
                "name_of_issuer": "OLD ROW",
                "value_usd": Decimal("100"),
                "shares": Decimal("1"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("1"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
            }
        ],
    )
    await holding_repo.bulk_insert(
        filing_id=amendment.id,
        holdings=[
            {
                "cusip": "222222222",
                "name_of_issuer": "AMEND ROW",
                "value_usd": Decimal("200"),
                "shares": Decimal("2"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("2"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
            }
        ],
    )
    await db_session.commit()

    rows = await holding_repo.list_by_filer_at_period(filer.id, period)
    assert [r.cusip for r in rows] == ["222222222"]


async def test_holding_repo_list_by_stock_returns_join_triples(
    db_session: AsyncSession,
) -> None:
    """list_by_stock returns (holding, filing, filer) triples with the
    most recent filing per stock first."""
    # Two filers, both holding the same stock_id; pick latest.
    f1 = await _mk_filer(db_session, cik="0003000003", name="Filer A")
    f2 = await _mk_filer(db_session, cik="0003000004", name="Filer B")
    stock = Stock(symbol="AAPL", name="Apple", market=Market.US_NASDAQ)
    db_session.add(stock)
    await db_session.commit()
    await db_session.refresh(stock)

    filing1 = await _mk_filing(db_session, f1.id, accession="s-a-1", period=date(2025, 9, 30))
    filing2 = await _mk_filing(db_session, f2.id, accession="s-b-1", period=date(2025, 12, 31))

    repo = F13HoldingRepo(db_session)
    await repo.bulk_insert(
        filing_id=filing1.id,
        holdings=[
            {
                "cusip": "037833100",
                "name_of_issuer": "APPLE INC",
                "value_usd": Decimal("1000"),
                "shares": Decimal("10"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("10"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
                "stock_id": stock.id,
            }
        ],
    )
    await repo.bulk_insert(
        filing_id=filing2.id,
        holdings=[
            {
                "cusip": "037833100",
                "name_of_issuer": "APPLE INC",
                "value_usd": Decimal("2000"),
                "shares": Decimal("20"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("20"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
                "stock_id": stock.id,
            }
        ],
    )
    await db_session.commit()

    rows = await repo.list_by_stock(stock.id, limit=10)
    assert len(rows) == 2
    # Latest period (Filer B / Q4 2025) first
    first_holding, first_filing, first_filer = rows[0]
    assert first_filer.name == "Filer B"
    assert first_filing.report_period_end == date(2025, 12, 31)
    assert first_holding.shares == Decimal("20")


async def test_holding_repo_list_by_cusip_works_without_stock(
    db_session: AsyncSession,
) -> None:
    """list_by_cusip fallback path when CUSIP is not yet mapped to a stock."""
    filer = await _mk_filer(db_session, cik="0003000005")
    filing = await _mk_filing(db_session, filer.id, accession="cusip-1")
    repo = F13HoldingRepo(db_session)
    await repo.bulk_insert(
        filing_id=filing.id,
        holdings=[
            {
                "cusip": "999999999",
                "name_of_issuer": "UNMAPPED CO",
                "value_usd": Decimal("500"),
                "shares": Decimal("5"),
                "investment_discretion": "SOLE",
                "voting_authority_sole": Decimal("5"),
                "voting_authority_shared": Decimal("0"),
                "voting_authority_none": Decimal("0"),
                # stock_id intentionally omitted — Phase 1 lazy mapping
            }
        ],
    )
    await db_session.commit()

    rows = await repo.list_by_cusip("999999999")
    assert len(rows) == 1
    h, f, fr = rows[0]
    assert h.cusip == "999999999"
    assert f.id == filing.id
    assert fr.id == filer.id
