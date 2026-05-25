"""Generic Uni-Seeker CSV adapter — the original Y2 Round 4 format.

This adapter reproduces the canonical CSV shape that
`CsvImportService._validate_row` originally supported:

    trade_date,action,symbol,market,quantity,price,fee,tax,note

It serves two roles:

1. Backward compatibility — users who exported their data with the
   Y2 template still drop the same file in and it Just Works.
2. Fallback during auto-detect — when no broker-specific adapter
   claims the file, we hand it to this one. If the header doesn't
   match either, the service surfaces the standard
   `invalid_csv_format` 422 to the API layer.
"""

from __future__ import annotations

import csv
import io
from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_DIVIDEND,
    ACTION_SELL,
    ACTION_SPLIT,
    ParsedRow,
)

# Canonical column order. Must match the Y2 template — frontend tooltip
# and the existing `test_holdings_csv_import` integration suite both
# assert on this exact list.
REQUIRED_HEADER = [
    "trade_date",
    "action",
    "symbol",
    "market",
    "quantity",
    "price",
    "fee",
    "tax",
    "note",
]


# Dividend-shaped action tokens we explicitly reject (they live in the
# /holdings/dividends endpoint, not the trade log).
_DIVIDEND_TOKENS = {"DIVIDEND", "DIV", "CASH_DIV", "STOCK_DIV", "SPLIT"}


class GenericCsvParser:
    """Adapter for the canonical Uni-Seeker CSV format."""

    BROKER_KEY = "generic"
    DISPLAY_NAME = "Uni-Seeker 通用格式"
    # Header is a verbatim match — we use the joined string as the
    # marker so auto-detect can spot it. Anything else falls through.
    EXPECTED_HEADERS: tuple[str, ...] = (",".join(REQUIRED_HEADER),)

    def can_handle(self, csv_content: str) -> bool:
        first_line = (csv_content.splitlines() or [""])[0]
        # Tolerate trailing whitespace + stray BOM.
        normalized = first_line.strip().lstrip("﻿")
        return normalized == ",".join(REQUIRED_HEADER)

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader, None)
        if not header or [h.strip() for h in header] != REQUIRED_HEADER:
            # Surface to the service as a header failure so the API
            # layer returns 422 invalid_csv_format — matches the legacy
            # Y2 behaviour exactly.
            raise ValueError("invalid_csv_format: missing or malformed header")

        out: list[ParsedRow] = []
        for idx, raw in enumerate(reader, start=2):
            if not raw or all(not (c or "").strip() for c in raw):
                continue
            out.append(self._parse_row(idx, raw))
        return out

    def _parse_row(self, row_index: int, raw: list[str]) -> ParsedRow:
        cols = list(raw) + [""] * (len(REQUIRED_HEADER) - len(raw))
        (
            trade_date_s,
            action_s,
            symbol_s,
            market_s,
            qty_s,
            price_s,
            fee_s,
            tax_s,
            note_s,
        ) = (cols[i].strip() for i in range(len(REQUIRED_HEADER)))

        action_upper = action_s.upper()
        action: str = action_upper

        # Defaults so we can always return a ParsedRow even when invalid.
        qty = Decimal("0")
        price = Decimal("0")
        fee = Decimal("0")
        tax = Decimal("0")
        trade_date = date_type.today()
        error: str | None = None

        if action_upper in _DIVIDEND_TOKENS:
            error = "dividend_actions_not_supported"
            # Keep recognisable category so downstream tooling can group.
            action = ACTION_DIVIDEND if action_upper != "SPLIT" else ACTION_SPLIT
        elif action_upper not in (ACTION_BUY, ACTION_SELL):
            error = "invalid_action"

        if error is None:
            try:
                qty = Decimal(qty_s)
                if qty <= Decimal("0"):
                    error = "invalid_quantity"
            except InvalidOperation:
                error = "invalid_quantity"

        if error is None:
            try:
                price = Decimal(price_s)
                if price <= Decimal("0"):
                    error = "invalid_price"
            except InvalidOperation:
                error = "invalid_price"

        if error is None:
            try:
                fee = Decimal(fee_s) if fee_s else Decimal("0")
                if fee < Decimal("0"):
                    error = "invalid_fee"
            except InvalidOperation:
                error = "invalid_fee"

        if error is None:
            try:
                tax = Decimal(tax_s) if tax_s else Decimal("0")
                if tax < Decimal("0"):
                    error = "invalid_tax"
            except InvalidOperation:
                error = "invalid_tax"

        if error is None:
            try:
                trade_date = date_type.fromisoformat(trade_date_s)
            except ValueError:
                error = "invalid_trade_date"

        if error is None and not symbol_s:
            error = "missing_symbol"

        # Market accepted verbatim — service layer validates against
        # the Market enum at write time.
        return ParsedRow(
            row_index=row_index,
            action=action,
            symbol=symbol_s.upper(),
            market=market_s or None,
            quantity=qty,
            price=price,
            fee=fee,
            tax=tax,
            trade_date=trade_date,
            note=note_s or None,
            currency="USD",  # service overrides via market if needed
            raw_row=dict(zip(REQUIRED_HEADER, cols, strict=False)),
            error=error,
        )


__all__ = ["REQUIRED_HEADER", "GenericCsvParser"]
