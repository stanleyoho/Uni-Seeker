"""Unit tests for ``app.modules.institutional.parser``.

Covers happy path, namespace variants, missing/optional fields, malformed
input, and the long-vs-options summary split (spec §3.3 Q3).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.institutional.parser import (
    ParseError,
    is_valid_cusip,
    parse_infotable_xml,
    summarize_filing,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_XML = FIXTURES / "sample_13f_infotable.xml"


# ───────────────────────── XML strings used inline ─────────────────────────


_NO_NS_XML = """<?xml version="1.0"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>2000</value>
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

_NS_PREFIX_XML = """<?xml version="1.0"?>
<ns1:informationTable xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <ns1:infoTable>
    <ns1:nameOfIssuer>TESLA INC</ns1:nameOfIssuer>
    <ns1:cusip>88160R101</ns1:cusip>
    <ns1:value>3000</ns1:value>
    <ns1:shrsOrPrnAmt>
      <ns1:sshPrnamt>50</ns1:sshPrnamt>
      <ns1:sshPrnamtType>SH</ns1:sshPrnamtType>
    </ns1:shrsOrPrnAmt>
    <ns1:investmentDiscretion>SOLE</ns1:investmentDiscretion>
    <ns1:votingAuthority>
      <ns1:Sole>50</ns1:Sole>
      <ns1:Shared>0</ns1:Shared>
      <ns1:None>0</ns1:None>
    </ns1:votingAuthority>
  </ns1:infoTable>
</ns1:informationTable>
"""

_EMPTY_INFOTABLE_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"/>
"""

_MALFORMED_XML = "<not-well-formed><missing-close>"


# ───────────────────────── tests ─────────────────────────


def test_parse_infotable_xml_happy_path() -> None:
    xml = SAMPLE_XML.read_text()
    holdings = parse_infotable_xml(xml)
    assert len(holdings) == 3

    # First row: NVIDIA pure stock
    nvda_stock = holdings[0]
    assert nvda_stock.cusip == "67066G104"
    assert nvda_stock.name_of_issuer == "NVIDIA CORP"
    assert nvda_stock.put_call is None
    assert nvda_stock.shares == Decimal("10000")
    assert nvda_stock.value_usd == Decimal("1500000") * Decimal("1000")  # 1.5B
    assert nvda_stock.shares_or_principal_type == "SH"
    assert nvda_stock.investment_discretion == "SOLE"

    # Second row: NVIDIA CALL option
    nvda_call = holdings[1]
    assert nvda_call.put_call == "CALL"

    # Third row: MICROSOFT PUT option
    msft_put = holdings[2]
    assert msft_put.put_call == "PUT"
    assert msft_put.investment_discretion == "SHARED"
    assert msft_put.voting_authority_shared == Decimal("2500")


def test_parse_handles_namespace_v1_vs_v2() -> None:
    # Bare-no-namespace
    no_ns = parse_infotable_xml(_NO_NS_XML)
    assert len(no_ns) == 1
    assert no_ns[0].cusip == "037833100"

    # Prefixed namespace
    with_ns = parse_infotable_xml(_NS_PREFIX_XML)
    assert len(with_ns) == 1
    assert with_ns[0].cusip == "88160R101"
    assert with_ns[0].name_of_issuer == "TESLA INC"


def test_parse_missing_put_call_returns_none() -> None:
    holdings = parse_infotable_xml(_NO_NS_XML)
    # Apple row has no <putCall> element at all → must be None.
    assert holdings[0].put_call is None


def test_parse_empty_xml_returns_empty_list() -> None:
    # Both an empty <informationTable> element and an empty string return [].
    assert parse_infotable_xml(_EMPTY_INFOTABLE_XML) == []
    assert parse_infotable_xml("") == []


def test_parse_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_infotable_xml(_MALFORMED_XML)


def test_summarize_filing_separates_long_vs_options() -> None:
    holdings = parse_infotable_xml(SAMPLE_XML.read_text())
    summary = summarize_filing(holdings)

    # Long-only = NVDA stock @ 1,500,000 thousand = $1.5B
    assert summary.total_value_usd == Decimal("1500000") * Decimal("1000")
    # Options = NVDA CALL (500k thousand) + MSFT PUT (250k thousand) = $750M
    expected_options = (Decimal("500000") + Decimal("250000")) * Decimal("1000")
    assert summary.options_notional_usd == expected_options
    assert summary.total_positions == 3


def test_summarize_filing_options_notional_includes_both_put_and_call() -> None:
    holdings = parse_infotable_xml(SAMPLE_XML.read_text())
    summary = summarize_filing(holdings)

    # CALL: 500,000 thousand ; PUT: 250,000 thousand → total $750M notional
    assert summary.options_notional_usd == Decimal("750000000")


def test_is_valid_cusip_9_chars() -> None:
    assert is_valid_cusip("67066G104") is True
    assert is_valid_cusip("037833100") is True
    assert is_valid_cusip("12345678") is False  # 8 chars
    assert is_valid_cusip("1234567890") is False  # 10 chars


def test_is_valid_cusip_rejects_special_chars() -> None:
    assert is_valid_cusip("67066G@04") is False
    assert is_valid_cusip("670 6G104") is False
    assert is_valid_cusip("") is False
    assert is_valid_cusip(None) is False  # type: ignore[arg-type]


def test_parse_value_already_unrolled_to_full_usd() -> None:
    """<value>1500000</value> means 1.5B USD (×1000 unroll done by parser)."""
    holdings = parse_infotable_xml(SAMPLE_XML.read_text())
    nvda = holdings[0]
    # Raw XML: 1500000 (thousands). Parser must surface 1,500,000,000.
    assert nvda.value_usd == Decimal("1500000000")
