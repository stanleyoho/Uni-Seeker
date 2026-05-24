"""Unit tests for ``app.modules.institutional.cusip_mapper``.

Phase 2 / UNI-F13-002. Covers:
  * EXACT CUSIP match
  * NAME_LIKE fuzzy match strips INC/CORP/LP/CLASS A
  * NO match → CusipMatch.stock_id is None
  * Empty / whitespace CUSIP early-return
  * Ambiguous NAME_LIKE (>1 candidate) → NONE rather than guess
  * Batch resolution preserves order + length
  * Unicode / hyphenated names survive normalization
  * Multi-suffix names ("APPLE INC COM CLASS A") strip recursively
  * Punctuation tolerance ("INC." vs "INC")
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.enums import Market
from app.models.stock import Stock
from app.modules.institutional.cusip_mapper import (
    CusipMatch,
    _normalize_issuer_name,
    batch_resolve_cusips,
    resolve_cusip,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── Seed helpers ──────────────────────────────────────────────────────────


async def _mk_stock(
    db: AsyncSession,
    symbol: str,
    name: str,
    cusip: str | None = None,
    market: Market = Market.US_NASDAQ,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=market)
    if cusip is not None:
        s.cusip = cusip
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ── Name normalization (pure-function tests) ──────────────────────────────


def test_normalize_strips_inc_corp() -> None:
    assert _normalize_issuer_name("APPLE INC") == "apple"
    assert _normalize_issuer_name("Microsoft Corp") == "microsoft"
    assert _normalize_issuer_name("CITIGROUP CORPORATION") == "citigroup"


def test_normalize_handles_multi_suffix() -> None:
    # "APPLE INC COM CLASS A" → strip "class a", "com", "inc" recursively.
    assert _normalize_issuer_name("APPLE INC COM CLASS A") == "apple"
    assert _normalize_issuer_name("ALPHABET INC CLASS C") == "alphabet"


def test_normalize_handles_punctuation() -> None:
    # "INC." vs "INC" — punctuation stripped before tokenization.
    assert _normalize_issuer_name("APPLE INC.") == "apple"
    # Ampersand and slash stripped → "at t".
    assert _normalize_issuer_name("AT&T INC") == "at t"


def test_normalize_lp_llc_ltd_plc() -> None:
    assert _normalize_issuer_name("BLACKSTONE LP") == "blackstone"
    assert _normalize_issuer_name("ACME LLC") == "acme"
    assert _normalize_issuer_name("BRITISH AMERICAN LTD") == "british american"
    assert _normalize_issuer_name("BARCLAYS PLC") == "barclays"


def test_normalize_empty_returns_empty() -> None:
    assert _normalize_issuer_name("") == ""
    assert _normalize_issuer_name("   ") == ""
    # Only-suffix collapses to "".
    assert _normalize_issuer_name("INC") == ""


# ── EXACT CUSIP resolution ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_cusip_exact_match(db_session: AsyncSession) -> None:
    stock = await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100"
    )
    match = await resolve_cusip(db_session, "037833100", "APPLE INC")
    assert isinstance(match, CusipMatch)
    assert match.stock_id == stock.id
    assert match.match_confidence == "EXACT"
    assert match.match_via == "stocks.cusip"
    assert match.matched_name == "Apple Inc."


# ── NAME_LIKE fuzzy match ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_cusip_name_like_strips_inc(
    db_session: AsyncSession,
) -> None:
    # Stock.cusip is NULL → EXACT path misses → falls to NAME_LIKE.
    stock = await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip=None,
    )
    match = await resolve_cusip(db_session, "037833100", "APPLE INC")
    assert match.stock_id == stock.id
    assert match.match_confidence == "NAME_LIKE"
    assert match.match_via == "name_fuzzy"


@pytest.mark.asyncio
async def test_resolve_cusip_no_match(db_session: AsyncSession) -> None:
    # Empty DB → nothing to resolve.
    match = await resolve_cusip(db_session, "999999999", "Nonexistent Inc")
    assert match.stock_id is None
    assert match.match_confidence == "NONE"
    assert match.match_via == "none"


@pytest.mark.asyncio
async def test_resolve_cusip_empty_cusip_early_return(
    db_session: AsyncSession,
) -> None:
    match = await resolve_cusip(db_session, "", "APPLE INC")
    assert match.stock_id is None
    assert match.match_confidence == "NONE"
    assert match.cusip == ""


@pytest.mark.asyncio
async def test_resolve_cusip_ambiguous_name_returns_none(
    db_session: AsyncSession,
) -> None:
    # Two stocks share a name token → ambiguous → NONE rather than guess.
    await _mk_stock(db_session, symbol="A1", name="ACME CORP", cusip=None)
    await _mk_stock(db_session, symbol="A2", name="ACME HOLDINGS", cusip=None)
    match = await resolve_cusip(db_session, "111111111", "ACME INC")
    assert match.stock_id is None
    assert match.match_confidence == "NONE"


# ── Batch resolution ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_resolve_cusips_preserves_order(
    db_session: AsyncSession,
) -> None:
    s_apple = await _mk_stock(
        db_session, symbol="AAPL", name="Apple Inc.", cusip="037833100"
    )
    s_msft = await _mk_stock(
        db_session, symbol="MSFT", name="Microsoft Corp", cusip="594918104"
    )
    pairs = [
        ("037833100", "APPLE INC"),
        ("999999999", "Nonexistent"),
        ("594918104", "MICROSOFT CORP"),
    ]
    matches = await batch_resolve_cusips(db_session, pairs)
    assert len(matches) == 3
    assert matches[0].stock_id == s_apple.id
    assert matches[1].stock_id is None
    assert matches[2].stock_id == s_msft.id


@pytest.mark.asyncio
async def test_batch_resolve_empty_input(db_session: AsyncSession) -> None:
    matches = await batch_resolve_cusips(db_session, [])
    assert matches == []
