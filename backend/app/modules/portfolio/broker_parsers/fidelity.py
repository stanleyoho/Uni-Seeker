"""Fidelity History CSV adapter.

Assumed format::

    Run Date,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Amount ($)
    04/15/2026,YOU BOUGHT,NVDA,NVIDIA CORP,Cash,100,500.00,0.00,0.00,-50000.00
    04/16/2026,YOU SOLD,NVDA,NVIDIA CORP,Cash,50,510.00,0.00,0.00,25500.00

Fidelity ships an "Account History" export with verbose ALL-CAPS
action labels ("YOU BOUGHT", "YOU SOLD", "DIVIDEND RECEIVED", etc.)
and US-style M/D/Y dates with parenthesized USD columns. Amount is
signed (negative = debit) which we use as a tie-break when Quantity
is ambiguous.

Real-format caveat: Fidelity's "View Transactions → Download" form
varies slightly across account types. Stanley should validate the
exact header spellings (with vs. without "$" in column names).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_DIVIDEND,
    ACTION_SELL,
    ParsedRow,
)


_FIDELITY_MARKERS = ("Run Date,Action", "YOU BOUGHT", "YOU SOLD")


class FidelityParser:
    """Fidelity History CSV adapter."""

    BROKER_KEY = "fidelity"
    DISPLAY_NAME = "Fidelity"
    EXPECTED_HEADERS: tuple[str, ...] = _FIDELITY_MARKERS

    def can_handle(self, csv_content: str) -> bool:
        head = "\n".join(csv_content.splitlines()[:5])
        # First two markers gate header detection; the third helps when
        # users hand-stripped the header but left the data intact.
        if "Run Date,Action" in head:
            return True
        return "YOU BOUGHT" in head or "YOU SOLD" in head

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader, None)
        if not header or "Action" not in (",".join(header)):
            raise ValueError("invalid_csv_format: missing Fidelity header")
        header = [h.strip().lstrip("﻿") for h in header]

        out: list[ParsedRow] = []
        for idx, raw in enumerate(reader, start=2):
            if not raw or all(not (c or "").strip() for c in raw):
                continue
            out.append(self._parse_row(idx, raw, header))
        return out

    def _parse_row(
        self, row_index: int, raw: list[str], header: list[str]
    ) -> ParsedRow:
        def col(name: str) -> str:
            # Fidelity sometimes ships with or without the "($)" suffix.
            for candidate in (name, f"{name} ($)", f"{name}($)"):
                try:
                    i = header.index(candidate)
                except ValueError:
                    continue
                return raw[i].strip() if i < len(raw) else ""
            return ""

        def to_decimal(s: str) -> Decimal:
            cleaned = s.replace("$", "").replace(",", "").strip()
            if cleaned in ("", "-"):
                return Decimal("0")
            return Decimal(cleaned)

        date_s = col("Run Date")
        action_s = col("Action").upper()
        symbol = col("Symbol")
        qty_s = col("Quantity")
        price_s = col("Price")
        comm_s = col("Commission") or "0"
        fees_s = col("Fees") or "0"

        # Action mapping — Fidelity uses "YOU BOUGHT"/"YOU SOLD" prefix.
        if "BOUGHT" in action_s or action_s.startswith("BUY"):
            action = ACTION_BUY
        elif "SOLD" in action_s or action_s.startswith("SELL"):
            action = ACTION_SELL
        elif "DIVIDEND" in action_s or "DIV" in action_s.split():
            return ParsedRow(
                row_index=row_index,
                action=ACTION_DIVIDEND,
                symbol=symbol,
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=datetime.today().date(),
                currency="USD",
                raw_row=dict(zip(header, raw, strict=False)),
                error="dividend_actions_not_supported",
            )
        else:
            return ParsedRow(
                row_index=row_index,
                action=action_s,
                symbol=symbol,
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=datetime.today().date(),
                currency="USD",
                raw_row=dict(zip(header, raw, strict=False)),
                error="invalid_action",
            )

        trade_date = datetime.today().date()
        err: str | None = None
        try:
            trade_date = datetime.strptime(date_s, "%m/%d/%Y").date()
        except ValueError:
            try:
                trade_date = datetime.strptime(date_s, "%Y-%m-%d").date()
            except ValueError:
                err = "invalid_trade_date"

        qty = Decimal("0")
        price = Decimal("0")
        if err is None:
            try:
                qty = abs(to_decimal(qty_s))
                if qty <= Decimal("0"):
                    err = "invalid_quantity"
            except InvalidOperation:
                err = "invalid_quantity"
        if err is None:
            try:
                price = to_decimal(price_s)
                if price <= Decimal("0"):
                    err = "invalid_price"
            except InvalidOperation:
                err = "invalid_price"

        try:
            fee = to_decimal(comm_s) + to_decimal(fees_s)
        except InvalidOperation:
            fee = Decimal("0")

        if err is None and not symbol:
            err = "missing_symbol"

        return ParsedRow(
            row_index=row_index,
            action=action,
            symbol=symbol.upper(),
            market=None,
            quantity=qty,
            price=price,
            fee=fee,
            tax=Decimal("0"),
            trade_date=trade_date,
            note=col("Description") or None,
            currency="USD",
            raw_row=dict(zip(header, raw, strict=False)),
            error=err,
        )


__all__ = ["FidelityParser"]
