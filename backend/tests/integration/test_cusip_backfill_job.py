"""Integration tests for `app.services.institutional.cusip_backfill_job`.

Phase 2 / UNI-F13-002. Covers:
  C01 backfill_cusips_for_filer happy path (EXACT + NAME_LIKE + NONE)
  C02 idempotency — re-run on same data is no-op
  C03 still_unmapped count when name has no Stock candidate
  C04 EXACT supersedes NAME_LIKE — upgrade path on a second run after
      stocks.cusip is populated
  C05 backfill_stocks_from_filings populates Stock.cusip from confirmed
      F13Holding mappings
  C06 skip already-mapped F13Holding rows (stock_id IS NULL filter)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.db.models.institutional.holding import F13Holding
from app.models.enums import Market
from app.models.stock import Stock
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
)
from app.services.institutional.cusip_backfill_job import (
    backfill_cusips_for_filer,
    backfill_cusips_global,
    backfill_stocks_from_filings,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.institutional.filer import F13Filer
    from app.db.models.institutional.filing import F13Filing


# ── Shared helpers ────────────────────────────────────────────────────────


async def _mk_filer(
    db: AsyncSession,
    cik: str = "0009999001",
    name: str = "Backfill Test Fund",
) -> F13Filer:
    f = await F13FilerRepo(db).create(cik=cik, name=name)
    await db.commit()
    return f


async def _mk_filing(
    db: AsyncSession,
    filer_id: int,
    accession: str = "bf-acc-1",
    period: date = date(2025, 12, 31),
) -> F13Filing:
    f = await F13FilingRepo(db).create(
        filer_id=filer_id,
        accession_number=accession,
        form_type="13F-HR",
        report_period_end=period,
        filed_at=datetime(period.year, period.month, period.day, tzinfo=UTC),
        total_value_usd=Decimal("1000000"),
        options_notional_usd=Decimal("0"),
        total_positions=3,
        raw_xml_url=f"https://x/{accession}/infotable.xml",
    )
    await db.commit()
    return f


async def _mk_stock(
    db: AsyncSession,
    symbol: str,
    name: str,
    cusip: str | None = None,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=Market.US_NASDAQ)
    if cusip is not None:
        s.cusip = cusip
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


def _holding_payload(cusip: str, name: str) -> dict:
    return {
        "cusip": cusip,
        "name_of_issuer": name,
        "value_usd": Decimal("1000"),
        "shares": Decimal("10"),
        "investment_discretion": "SOLE",
        "voting_authority_sole": Decimal("10"),
        "voting_authority_shared": Decimal("0"),
        "voting_authority_none": Decimal("0"),
    }


# ─────────────────────────────────────────────────────────────────────────
# C01 — happy path
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C01_backfill_for_filer_happy_path(
    db_session: AsyncSession,
) -> None:
    # AAPL gets EXACT, MSFT gets NAME_LIKE, UNK gets NONE.
    await _mk_stock(db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100")
    await _mk_stock(db_session, symbol="MSFT", name="Microsoft Corp", cusip=None)

    filer = await _mk_filer(db_session, cik="0009990001")
    filing = await _mk_filing(db_session, filer.id, accession="c01")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[
            _holding_payload("037833100", "APPLE INC"),
            _holding_payload("594918104", "MICROSOFT CORP"),
            _holding_payload("999999999", "UNKNOWN ENTITY LTD"),
        ],
    )
    await db_session.commit()

    result = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()

    assert result["processed"] == 3
    assert result["exact_matches"] == 1
    assert result["fuzzy_matches"] == 1
    assert result["still_unmapped"] == 1


# ─────────────────────────────────────────────────────────────────────────
# C02 — idempotency
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C02_idempotent_rerun(db_session: AsyncSession) -> None:
    await _mk_stock(db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100")
    filer = await _mk_filer(db_session, cik="0009990002")
    filing = await _mk_filing(db_session, filer.id, accession="c02")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[_holding_payload("037833100", "APPLE INC")],
    )
    await db_session.commit()

    r1 = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    assert r1["exact_matches"] == 1
    assert r1["still_unmapped"] == 0

    # Re-run: nothing left to process because stock_id IS NULL filter
    # excludes the now-mapped row.
    r2 = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    assert r2["processed"] == 0
    assert r2["exact_matches"] == 0
    assert r2["fuzzy_matches"] == 0


# ─────────────────────────────────────────────────────────────────────────
# C03 — still_unmapped count
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C03_still_unmapped_when_no_candidate(
    db_session: AsyncSession,
) -> None:
    filer = await _mk_filer(db_session, cik="0009990003")
    filing = await _mk_filing(db_session, filer.id, accession="c03")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[
            _holding_payload("AAA111111", "OBSCURE FUND I LP"),
            _holding_payload("BBB222222", "ANOTHER MYSTERY CORP"),
        ],
    )
    await db_session.commit()

    result = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    assert result["processed"] == 2
    assert result["exact_matches"] == 0
    assert result["fuzzy_matches"] == 0
    assert result["still_unmapped"] == 2

    # Holdings retain stock_id = NULL.
    rows = (
        (await db_session.execute(select(F13Holding).where(F13Holding.filing_id == filing.id)))
        .scalars()
        .all()
    )
    assert all(r.stock_id is None for r in rows)


# ─────────────────────────────────────────────────────────────────────────
# C04 — EXACT supersedes NAME_LIKE (upgrade path)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C04_exact_supersedes_namelike_after_backfill(
    db_session: AsyncSession,
) -> None:
    # Round 1: Stock has NO cusip → first holding linked via NAME_LIKE
    # to apple_old. Then we add a *different* stock that carries the
    # CUSIP. After populating stocks.cusip, the upgrade path should
    # repoint the holding to the CUSIP-confirmed stock.
    apple_namelike = await _mk_stock(
        db_session,
        symbol="AAPL.OLD",
        name="Apple Inc.",
        cusip=None,
    )
    filer = await _mk_filer(db_session, cik="0009990004")
    filing = await _mk_filing(db_session, filer.id, accession="c04")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[_holding_payload("037833100", "APPLE INC")],
    )
    await db_session.commit()

    r1 = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    assert r1["fuzzy_matches"] == 1

    holding = (
        await db_session.execute(select(F13Holding).where(F13Holding.filing_id == filing.id))
    ).scalar_one()
    assert holding.stock_id == apple_namelike.id

    # Round 2: a "real" Apple stock with the CUSIP appears (e.g.
    # imported by a master sync). The next backfill should swap the
    # holding's stock_id to the CUSIP-confirmed one.
    apple_real = await _mk_stock(
        db_session,
        symbol="AAPL",
        name="Apple Inc. (NASDAQ)",
        cusip="037833100",
    )
    r2 = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    assert r2["upgraded"] == 1

    await db_session.refresh(holding)
    assert holding.stock_id == apple_real.id


# ─────────────────────────────────────────────────────────────────────────
# C05 — backfill_stocks_from_filings
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C05_backfill_stocks_from_filings_populates_cusip(
    db_session: AsyncSession,
) -> None:
    # AAPL stock has NO cusip; holding fuzzy-matches it. After backfill,
    # backfill_stocks_from_filings copies the holding's CUSIP onto AAPL.
    aapl = await _mk_stock(
        db_session,
        symbol="AAPL",
        name="Apple Inc.",
        cusip=None,
    )
    filer = await _mk_filer(db_session, cik="0009990005")
    filing = await _mk_filing(db_session, filer.id, accession="c05")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[_holding_payload("037833100", "APPLE INC")],
    )
    await db_session.commit()

    await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()

    stocks_result = await backfill_stocks_from_filings(db_session)
    await db_session.commit()
    assert stocks_result["stocks_updated"] == 1

    await db_session.refresh(aapl)
    assert aapl.cusip == "037833100"


# ─────────────────────────────────────────────────────────────────────────
# C06 — skip already-mapped holdings
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_C06_skip_already_mapped(db_session: AsyncSession) -> None:
    # Pre-mapped holding (set stock_id at insert) → backfill must not
    # double-process.
    aapl = await _mk_stock(db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100")
    filer = await _mk_filer(db_session, cik="0009990006")
    filing = await _mk_filing(db_session, filer.id, accession="c06")
    payload = _holding_payload("037833100", "APPLE INC")
    payload["stock_id"] = aapl.id  # already mapped at insert time
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[payload],
    )
    # Also insert an unmapped row that backfill *should* process.
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[_holding_payload("999999999", "ZZZ HOLDINGS LTD")],
    )
    await db_session.commit()

    result = await backfill_cusips_for_filer(db_session, filer.id)
    await db_session.commit()
    # Only the unmapped row is in the unmapped scan — exact = 0, fuzzy = 0,
    # still_unmapped = 1.
    assert result["processed"] == 1
    assert result["still_unmapped"] == 1

    # Global backfill mirrors the same skip behaviour.
    g = await backfill_cusips_global(db_session)
    await db_session.commit()
    assert g["processed"] == 1
    assert g["still_unmapped"] == 1
