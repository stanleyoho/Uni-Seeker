"""Integration tests for the FIGI-aware CUSIP mapper / backfill (Phase 3).

Covers ``app.modules.institutional.cusip_mapper.resolve_cusip_with_figi``,
``batch_resolve_cusips_with_figi``, and
``app.services.institutional.cusip_backfill_job.backfill_cusips_for_filer_with_figi``.

A stub OpenFigiClient (no real network) is injected — the production
client's HTTP layer is covered by the unit suite. We only assert the
4-layer routing logic here.
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
from app.modules.institutional.cusip_mapper import (
    batch_resolve_cusips_with_figi,
    resolve_cusip_with_figi,
)
from app.modules.institutional.openfigi_client import FigiMapping
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
)
from app.services.institutional.cusip_backfill_job import (
    backfill_cusips_for_filer_with_figi,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Stub FIGI client ──────────────────────────────────────────────────────


class _StubFigiClient:
    """Drop-in for :class:`OpenFigiClient` that returns a fixed mapping table.

    Records each call's ``cusips`` argument so we can assert that the
    batch path coalesces EXACT-misses into a *single* FIGI call.
    """

    def __init__(self, table: dict[str, str | None]) -> None:
        # cusip → ticker; None means "FIGI knows it but no US common stock"
        self._table = table
        self.calls: list[list[str]] = []

    async def map_cusips(self, cusips: list[str]) -> list[FigiMapping]:
        self.calls.append(list(cusips))
        out: list[FigiMapping] = []
        for c in cusips:
            ticker = self._table.get(c)
            out.append(
                FigiMapping(
                    cusip=c,
                    ticker=ticker,
                    name=f"{ticker} CO" if ticker else None,
                    exch_code="US" if ticker else None,
                    security_type="Common Stock" if ticker else None,
                    error=None if ticker else "no_us_common_stock",
                )
            )
        return out


# ── Seed helpers ──────────────────────────────────────────────────────────


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


async def _mk_filer(db: AsyncSession, cik: str, name: str = "Figi Test Fund"):
    f = await F13FilerRepo(db).create(cik=cik, name=name)
    await db.commit()
    return f


async def _mk_filing(db: AsyncSession, filer_id: int, accession: str):
    f = await F13FilingRepo(db).create(
        filer_id=filer_id,
        accession_number=accession,
        form_type="13F-HR",
        report_period_end=date(2025, 12, 31),
        filed_at=datetime(2026, 2, 14, tzinfo=UTC),
        total_value_usd=Decimal("1000000"),
        options_notional_usd=Decimal("0"),
        total_positions=3,
        raw_xml_url=f"https://x/{accession}/infotable.xml",
    )
    await db.commit()
    return f


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
# F01 — EXACT takes precedence over FIGI
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F01_resolve_cusip_with_figi_uses_exact_first(
    db_session: AsyncSession,
) -> None:
    aapl = await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100",
    )
    figi = _StubFigiClient({"037833100": "AAPL"})

    match = await resolve_cusip_with_figi(
        db_session, "037833100", "APPLE INC", figi_client=figi,
    )
    assert match.stock_id == aapl.id
    assert match.match_confidence == "EXACT"
    assert match.match_via == "stocks.cusip"
    # FIGI must not have been called — EXACT short-circuits.
    assert figi.calls == []


# ─────────────────────────────────────────────────────────────────────────
# F02 — EXACT miss → FIGI hit
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F02_resolve_cusip_with_figi_falls_through_to_figi(
    db_session: AsyncSession,
) -> None:
    # Stock exists but has no CUSIP — EXACT misses, FIGI resolves ticker
    # 'NVDA' which matches Stock.symbol.
    nvda = await _mk_stock(
        db_session, symbol="NVDA", name="NVIDIA Corp.", cusip=None,
    )
    figi = _StubFigiClient({"67066G104": "NVDA"})

    match = await resolve_cusip_with_figi(
        db_session, "67066G104", "NVIDIA CORP", figi_client=figi,
    )
    assert match.stock_id == nvda.id
    assert match.match_confidence == "FIGI"
    assert match.match_via == "openfigi"
    assert match.figi_ticker == "NVDA"
    assert figi.calls == [["67066G104"]]


# ─────────────────────────────────────────────────────────────────────────
# F03 — FIGI returns no ticker → NAME_LIKE
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F03_resolve_cusip_with_figi_falls_through_to_name_like(
    db_session: AsyncSession,
) -> None:
    msft = await _mk_stock(
        db_session, symbol="MSFT", name="Microsoft Corp", cusip=None,
    )
    # FIGI knows the CUSIP but has no US common stock candidate.
    figi = _StubFigiClient({"594918104": None})

    match = await resolve_cusip_with_figi(
        db_session, "594918104", "MICROSOFT CORP", figi_client=figi,
    )
    assert match.stock_id == msft.id
    assert match.match_confidence == "NAME_LIKE"
    assert match.match_via == "name_fuzzy"
    assert match.figi_ticker is None


# ─────────────────────────────────────────────────────────────────────────
# F04 — figi_client=None degrades to 3-layer behaviour
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F04_resolve_cusip_with_figi_skips_figi_when_client_none(
    db_session: AsyncSession,
) -> None:
    aapl = await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip=None,
    )
    # No FIGI client → only EXACT + NAME_LIKE available.
    match = await resolve_cusip_with_figi(
        db_session, "037833100", "APPLE INC", figi_client=None,
    )
    # CUSIP not on the stock row, so EXACT misses; NAME_LIKE picks it up.
    assert match.stock_id == aapl.id
    assert match.match_confidence == "NAME_LIKE"
    assert match.figi_ticker is None


# ─────────────────────────────────────────────────────────────────────────
# F05 — batch collects EXACT-misses into one FIGI call
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F05_batch_resolve_with_figi_collects_misses_efficiently(
    db_session: AsyncSession,
) -> None:
    # AAPL hits EXACT (cusip on row). NVDA + MSFT miss EXACT — they should
    # be collected into a single FIGI call.
    await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100",
    )
    await _mk_stock(
        db_session, symbol="NVDA", name="NVIDIA Corp.", cusip=None,
    )
    await _mk_stock(
        db_session, symbol="MSFT", name="Microsoft Corp", cusip=None,
    )

    figi = _StubFigiClient(
        {
            "67066G104": "NVDA",
            "594918104": "MSFT",
        }
    )

    pairs = [
        ("037833100", "APPLE INC"),   # EXACT
        ("67066G104", "NVIDIA CORP"), # FIGI
        ("594918104", "MICROSOFT CORP"),  # FIGI
        ("999999999", "ZZZ UNKNOWN"), # FIGI miss → NONE
    ]
    matches = await batch_resolve_cusips_with_figi(
        db_session, pairs, figi_client=figi,
    )

    assert len(matches) == 4
    assert matches[0].match_confidence == "EXACT"
    assert matches[1].match_confidence == "FIGI"
    assert matches[2].match_confidence == "FIGI"
    assert matches[3].match_confidence == "NONE"

    # Critical optimisation assertion: exactly ONE FIGI call for ALL the
    # EXACT-misses, not three. Calls list looks like:
    #   [["67066G104", "594918104", "999999999"]]
    assert len(figi.calls) == 1
    assert sorted(figi.calls[0]) == sorted(
        ["67066G104", "594918104", "999999999"]
    )


# ─────────────────────────────────────────────────────────────────────────
# F06 — backfill_cusips_for_filer_with_figi happy path
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_F06_backfill_cusips_for_filer_with_figi_happy_path(
    db_session: AsyncSession,
) -> None:
    # AAPL → EXACT (cusip on row).
    # NVDA → FIGI (no cusip on row; FIGI returns "NVDA" ticker; symbol matches).
    # MSFT → NAME_LIKE (FIGI doesn't know it; name fuzzy match wins).
    # ZZZ  → NONE.
    await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100",
    )
    await _mk_stock(
        db_session, symbol="NVDA", name="NVIDIA Corp.", cusip=None,
    )
    await _mk_stock(
        db_session, symbol="MSFT", name="Microsoft Corp", cusip=None,
    )

    filer = await _mk_filer(db_session, cik="0009993001")
    filing = await _mk_filing(db_session, filer.id, accession="f06")
    await F13HoldingRepo(db_session).bulk_insert(
        filing_id=filing.id,
        holdings=[
            _holding_payload("037833100", "APPLE INC"),
            _holding_payload("67066G104", "NVIDIA CORP"),
            _holding_payload("594918104", "MICROSOFT CORP"),
            _holding_payload("999999999", "ZZZ UNKNOWN ENTITY"),
        ],
    )
    await db_session.commit()

    figi = _StubFigiClient(
        {
            "67066G104": "NVDA",
            # MSFT CUSIP intentionally omitted → FIGI miss → NAME_LIKE.
        }
    )

    result = await backfill_cusips_for_filer_with_figi(
        db_session, filer.id, figi_client=figi,
    )
    await db_session.commit()

    assert result["processed"] == 4
    assert result["exact_matches"] == 1
    assert result["figi_matches"] == 1
    assert result["fuzzy_matches"] == 1
    assert result["still_unmapped"] == 1

    # Ensure stock_id was actually persisted on each holding.
    rows = (
        await db_session.execute(
            select(F13Holding).where(F13Holding.filing_id == filing.id)
        )
    ).scalars().all()
    by_cusip = {r.cusip: r for r in rows}
    assert by_cusip["037833100"].stock_id is not None
    assert by_cusip["67066G104"].stock_id is not None
    assert by_cusip["594918104"].stock_id is not None
    assert by_cusip["999999999"].stock_id is None
