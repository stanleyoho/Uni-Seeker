"""BrokerParser Protocol + ParsedRow dataclass — broker CSV adapter contract.

Round 10 — Phase 4+ broker-specific import. Each real broker exports a
wildly different CSV shape (column names, date format, encoding, action
vocabulary, multi-section layout). Rather than bolt every broker quirk
into a single `CsvImportService._validate_row`, we adopt a small
protocol: every broker has its own adapter that translates raw CSV
text into a list of `ParsedRow` records. The service then runs the
same downstream tier-check + bulk-write logic regardless of source.

Anti-coupling
-------------

This module is **pure domain**. No SQLAlchemy, no FastAPI, no I/O.
Adapters take a `str` and return a list of `ParsedRow` dataclasses —
the surrounding service layer is responsible for ORM mapping. This
keeps adapter unit tests trivial (no DB fixtures) and mirrors the
spec §11 R1/R3 rule already enforced for FIFO / cost-basis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from decimal import Decimal
from typing import Protocol, runtime_checkable

# Canonical action vocabulary used downstream by `PortfolioTradeService.
# record_trade`. Adapters MUST normalize their broker's vocabulary into
# one of these tokens (or surface a per-row error). DIVIDEND / SPLIT
# are recognised but rejected by the import service (the dedicated
# /holdings/dividends endpoint owns dividend bookkeeping).
ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_DIVIDEND = "DIVIDEND"
ACTION_SPLIT = "SPLIT"


@dataclass
class ParsedRow:
    """Normalized trade row — broker-format-agnostic.

    Each adapter emits a list of these. The CsvImportService takes the
    list and feeds successful rows into `PortfolioTradeService.record_trade`.

    Fields:
        row_index: 1-based against the original file. We use this for
            error reporting so users can find the offending row.
        action: One of {BUY, SELL, DIVIDEND, SPLIT}. The service rejects
            DIVIDEND / SPLIT (handled by a separate endpoint).
        symbol: Ticker, uppercased. TW stocks use the 4-digit code; US
            stocks use the alpha ticker.
        market: One of Market enum values or None (auto-detected by the
            service from currency/symbol pattern if missing).
        quantity / price / fee / tax: Decimals. The adapter guarantees
            positive quantity + price (or sets `error`).
        trade_date: Parsed date.
        note: Free-form text from the broker file (e.g. order id).
        currency: Per-broker default (USD for IB/Schwab/Fidelity, TWD
            for Yuanta/Fubon). Used only if the position needs creation.
        raw_row: Dict of original column → value for debug / audit.
        error: snake_case error code if this row failed parse. When set,
            the service surfaces the row as a failure without persisting.
    """

    row_index: int
    action: str
    symbol: str
    market: str | None
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal
    trade_date: date_type
    note: str | None = None
    currency: str = "USD"
    raw_row: dict | None = field(default=None, repr=False)
    error: str | None = None


@runtime_checkable
class BrokerParser(Protocol):
    """Per-broker CSV adapter.

    Implementations live in sibling files (interactive_brokers.py,
    yuanta.py, etc.). The service layer wires them into a registry
    and dispatches by broker_key or auto-detection.

    Class attributes:
        BROKER_KEY: stable wire identifier (e.g. "interactive_brokers").
            Sent over the API to pick this adapter explicitly.
        DISPLAY_NAME: human-readable label shown in the frontend dropdown.
        EXPECTED_HEADERS: tuple of substrings to scan for in the first
            handful of lines during auto-detection. Empty tuple = manual
            selection only (used by `generic`).

    Methods:
        parse: take the full CSV text and return normalized rows. May
            include rows with `error` set — the service treats them as
            per-row failures. Adapter-level fatal errors (no recognizable
            header anywhere) → raise ValueError so the service maps to 422.
        can_handle: cheap detection heuristic. Adapter inspects the first
            few lines for unique markers. Returns True when this adapter
            is the right choice. Used during auto-detect when broker_key
            is None.
    """

    BROKER_KEY: str
    DISPLAY_NAME: str
    EXPECTED_HEADERS: tuple[str, ...]

    def parse(self, csv_content: str) -> list[ParsedRow]: ...

    def can_handle(self, csv_content: str) -> bool: ...


__all__ = [
    "ACTION_BUY",
    "ACTION_DIVIDEND",
    "ACTION_SELL",
    "ACTION_SPLIT",
    "BrokerParser",
    "ParsedRow",
]
