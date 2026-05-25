"""13F infotable XML parser — pure module, no I/O.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§3.3 (infoTable schema), §7.1 (parser contract), §11.R1 (schema-change risk).

Why ``xml.etree.ElementTree`` and not ``lxml`` (spec §6.1 originally proposed
``lxml``):
- ``lxml`` is **not** a current backend dependency (see ``pyproject.toml``);
  task constraints forbid adding new top-level deps.
- Python 3.12's stdlib ElementTree supports wildcard namespace matching
  (``{*}infoTable``) which is sufficient for the namespace variants SEC
  emits across years.
- All parsing is single-pass, in-memory; no streaming or XPath features
  needed at Phase 1 scale (the largest 13F filings — Berkshire — are
  ~1MB after gzip, well under ``ET.fromstring`` limits).

Pure-function rules (anti-coupling §11.2):
- No network calls. Caller hands us already-fetched text/bytes.
- No DB. We return dataclasses; service layer persists.
- No FastAPI / Pydantic. Just stdlib + Decimal.

The ``value_usd`` field of each ``ParsedHolding`` is already
``raw_value × 1000`` — the XML's ``<value>`` is reported in thousands per
the SEC 13F instructions, and we unroll once at the parser boundary so
no downstream caller has to remember the multiplier.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from collections.abc import Iterable

import structlog

__all__ = [
    "FilingSummary",
    "ParseError",
    "ParsedHolding",
    "is_valid_cusip",
    "parse_infotable_xml",
    "summarize_filing",
]

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_THOUSAND = Decimal("1000")


# ───────────────────────── public types ─────────────────────────


class ParseError(ValueError):
    """Raised on malformed 13F XML that cannot be parsed at all.

    Per-row validation issues (missing optional fields, invalid CUSIPs)
    are logged as warnings and the row is skipped — partial parse is
    always preferable to a hard fail when a filer has hundreds of rows.
    Only catastrophic XML errors (not well-formed, wrong root element)
    raise ``ParseError``.
    """


@dataclass(frozen=True)
class ParsedHolding:
    """One row of a 13F infotable.

    Per spec §3.3 / §11.R6, the natural key for a row inside a filing is
    ``(cusip, put_call)`` — same CUSIP can legitimately appear multiple
    times under different ``putCall`` values (e.g. common stock + CALL).
    """

    cusip: str
    name_of_issuer: str
    value_usd: Decimal  # already ×1000 unrolled to actual USD
    shares: Decimal | None  # None when quantity_type='PRN' (principal amt)
    shares_or_principal_type: str  # "SH" | "PRN"
    put_call: str | None  # "PUT" | "CALL" | None
    investment_discretion: str  # "SOLE" | "SHARED" | "NONE"
    voting_authority_sole: Decimal
    voting_authority_shared: Decimal
    voting_authority_none: Decimal


@dataclass(frozen=True)
class FilingSummary:
    """Filing-level totals computed from a list of ``ParsedHolding``.

    Per spec §3.3 (Q3 decision) we separate **pure 13F long** value
    (rows with ``put_call is None``) from **options notional** (rows
    with ``put_call in {"PUT","CALL"}``). The UI surfaces both numbers
    because SEC 13F mixes them in ``<value>`` and naive Σ overstates AUM.
    """

    total_value_usd: Decimal  # Σ over rows where put_call is None
    options_notional_usd: Decimal  # Σ over rows where put_call in {PUT,CALL}
    total_positions: int  # count of all parsed rows


# ───────────────────────── public API ─────────────────────────


def parse_infotable_xml(xml_content: str | bytes) -> list[ParsedHolding]:
    """Parse a 13F ``infotable.xml`` into a list of ``ParsedHolding``.

    Args:
        xml_content: raw XML text (str) or bytes. Both accepted because
            ``EdgarClient.fetch_filing_xml`` returns ``str`` but tests
            may pass bytes loaded directly from disk.

    Returns:
        List of parsed rows. **Empty list** is a valid result for an
        empty filing (filer reported via 13F-NT but no infoTable holdings).

    Raises:
        ParseError: when XML is not well-formed or has no recognizable
            root element (i.e. wrong file type).
    """
    if xml_content is None or (isinstance(xml_content, (str, bytes)) and len(xml_content) == 0):
        # Empty input is a valid "no holdings" filing.
        return []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ParseError(f"malformed 13F XML: {exc}") from exc

    # Accept any namespace via wildcard. ElementTree's ``{*}`` matches
    # any namespace URI, including none (bare elements).
    info_tables = list(root.iterfind(".//{*}infoTable"))
    if not info_tables and _local_name(root) == "infoTable":
        # The root itself might already be an infoTable (uncommon but seen
        # in malformed exports).
        info_tables = [root]

    holdings: list[ParsedHolding] = []
    for el in info_tables:
        parsed = _parse_one_info_table(el)
        if parsed is not None:
            holdings.append(parsed)
    return holdings


def summarize_filing(holdings: Iterable[ParsedHolding]) -> FilingSummary:
    """Compute filing-level totals from already-parsed rows.

    Pure function; safe to call multiple times. Separates long-only
    market value from options notional per spec §3.3 Q3 (c).
    """
    long_total = _ZERO
    options_total = _ZERO
    count = 0
    for h in holdings:
        count += 1
        if h.put_call is None:
            long_total += h.value_usd
        else:
            options_total += h.value_usd
    return FilingSummary(
        total_value_usd=long_total,
        options_notional_usd=options_total,
        total_positions=count,
    )


def is_valid_cusip(cusip: str) -> bool:
    """Lightweight CUSIP validity check.

    CUSIPs are 9-character alphanumeric (uppercase). Phase 1 does **not**
    verify the check-digit (last digit) — many 13F filings emit 8-char
    CUSIPs without the check digit, and we want to accept those to avoid
    silently dropping legitimate rows. Stricter validation can land in
    Phase 2 once we know real-world hit-rates.
    """
    if not cusip or not isinstance(cusip, str):
        return False
    s = cusip.strip().upper()
    if len(s) != 9:
        return False
    return all(c.isalnum() for c in s)


# ───────────────────────── private parsing helpers ─────────────────────────


def _parse_one_info_table(el: ET.Element) -> ParsedHolding | None:
    """Parse one ``<infoTable>`` element. Returns None on row-level errors."""
    cusip_raw = _find_text(el, "cusip")
    if cusip_raw is None:
        logger.warning("13f_row_missing_cusip", element=_local_name(el))
        return None

    cusip = cusip_raw.strip().upper()
    if not is_valid_cusip(cusip):
        logger.warning("13f_row_invalid_cusip", cusip=cusip_raw)
        return None

    name_of_issuer = (_find_text(el, "nameOfIssuer") or "").strip()
    if not name_of_issuer:
        # Name is required by 13F instructions; skip if absent.
        logger.warning("13f_row_missing_name", cusip=cusip)
        return None

    # ``<value>`` is reported in thousands of USD per SEC 13F instructions.
    raw_value = _find_text(el, "value")
    try:
        value_thousands = Decimal(raw_value) if raw_value is not None else _ZERO
    except (InvalidOperation, ValueError):
        logger.warning("13f_row_invalid_value", cusip=cusip, raw=raw_value)
        return None
    value_usd = value_thousands * _THOUSAND

    # shrsOrPrnAmt contains both the count and the type. Both nested.
    shrs_el = _find_child(el, "shrsOrPrnAmt")
    shrs_amt_text = _find_text(shrs_el, "sshPrnamt") if shrs_el is not None else None
    shrs_type = (_find_text(shrs_el, "sshPrnamtType") if shrs_el is not None else None) or ""
    shrs_type = shrs_type.strip().upper() or "SH"

    shares: Decimal | None
    if shrs_amt_text is None:
        shares = None
    else:
        try:
            shares = Decimal(shrs_amt_text)
        except (InvalidOperation, ValueError):
            logger.warning("13f_row_invalid_shares", cusip=cusip, raw=shrs_amt_text)
            shares = None

    # PRN rows hold a principal amount, not shares — surface that distinction
    # by setting ``shares = None`` to avoid double-counting.
    shares_for_field = None if shrs_type == "PRN" else shares

    # Optional fields.
    put_call_raw = _find_text(el, "putCall")
    put_call = put_call_raw.strip().upper() if put_call_raw else None
    if put_call == "":
        put_call = None
    if put_call is not None and put_call not in {"PUT", "CALL"}:
        # Unknown value — preserve for visibility but log.
        logger.warning("13f_row_unknown_put_call", cusip=cusip, raw=put_call_raw)

    discretion = (_find_text(el, "investmentDiscretion") or "SOLE").strip().upper()

    voting_el = _find_child(el, "votingAuthority")
    voting_sole = _decimal_or_zero(_find_text(voting_el, "Sole") if voting_el is not None else None)
    voting_shared = _decimal_or_zero(
        _find_text(voting_el, "Shared") if voting_el is not None else None
    )
    voting_none = _decimal_or_zero(_find_text(voting_el, "None") if voting_el is not None else None)

    return ParsedHolding(
        cusip=cusip,
        name_of_issuer=name_of_issuer,
        value_usd=value_usd,
        shares=shares_for_field,
        shares_or_principal_type=shrs_type,
        put_call=put_call,
        investment_discretion=discretion,
        voting_authority_sole=voting_sole,
        voting_authority_shared=voting_shared,
        voting_authority_none=voting_none,
    )


def _local_name(el: ET.Element) -> str:
    """Strip the ``{namespace}`` prefix from a tag, returning the local name."""
    tag = el.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag or ""


def _find_child(el: ET.Element | None, local_name: str) -> ET.Element | None:
    """Find first direct child with the given local name (namespace-agnostic).

    ElementTree's wildcard search ``{*}name`` works for descendants but
    behaves unexpectedly with ``find()`` at root level on some 3.12 builds
    — we do a manual loop to be deterministic.
    """
    if el is None:
        return None
    for child in el:
        if _local_name(child) == local_name:
            return child
    return None


def _find_text(el: ET.Element | None, local_name: str) -> str | None:
    """Return ``.text`` of the first descendant with matching local name."""
    if el is None:
        return None
    if _local_name(el) == local_name:
        return el.text
    # First try a direct child (most common shape).
    direct = _find_child(el, local_name)
    if direct is not None:
        return direct.text
    # Fall back to the first descendant.
    for descendant in el.iter():
        if _local_name(descendant) == local_name:
            return descendant.text
    return None


def _decimal_or_zero(raw: str | None) -> Decimal:
    if raw is None:
        return _ZERO
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        return _ZERO
