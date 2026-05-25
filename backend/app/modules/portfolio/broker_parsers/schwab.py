"""Charles Schwab Transactions CSV adapter.

Assumed format::

    Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount
    04/15/2026,Buy,NVDA,NVIDIA CORP,100,500.00,$0.00,$50000.00
    04/16/2026,Sell,NVDA,NVIDIA CORP,50,510.00,$0.00,$25500.00

Schwab's export ships dollar-prefixed numbers (``$0.00``) and US-style
M/D/Y dates. Action vocabulary uses capitalised English ("Buy"/"Sell";
also "Reinvest"/"Dividend"/"Cash In Lieu" which we reject as dividends).

Real-format caveat: Schwab has multiple export shapes — the "Brokerage"
transactions page uses the form above, while "Realized Gain/Loss"
exports look different. Stanley should confirm against the latest
brokerage download.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_DIVIDEND,
    ACTION_SELL,
    ParsedRow,
)

_SCHWAB_MARKERS = ("Date,Action,Symbol", "Fees & Comm")


_ACTION_MAP = {
    "Buy": ACTION_BUY,
    "Sell": ACTION_SELL,
    "Buy to Open": ACTION_BUY,
    "Sell to Close": ACTION_SELL,
    "Reinvest Shares": ACTION_BUY,
}


class SchwabParser:
    """Charles Schwab Transactions CSV adapter."""

    BROKER_KEY = "schwab"
    DISPLAY_NAME = "Charles Schwab"
    EXPECTED_HEADERS: tuple[str, ...] = _SCHWAB_MARKERS

    def can_handle(self, csv_content: str) -> bool:
        head = "\n".join(csv_content.splitlines()[:5])
        # Schwab and Fidelity overlap on "Action,Symbol"; disambiguate
        # by Schwab's "Fees & Comm" column header, which Fidelity does
        # NOT ship (Fidelity uses "Commission ($),Fees ($)"). Also
        # reject when "Run Date" appears (Fidelity's leading column).
        if "Run Date" in head:
            return False
        return "Fees & Comm" in head

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader, None)
        if not header or "Action" not in header or "Symbol" not in header:
            raise ValueError("invalid_csv_format: missing Schwab header")
        header = [h.strip().lstrip("﻿") for h in header]

        out: list[ParsedRow] = []
        for idx, raw in enumerate(reader, start=2):
            if not raw or all(not (c or "").strip() for c in raw):
                continue
            out.append(self._parse_row(idx, raw, header))
        return out

    def _parse_row(self, row_index: int, raw: list[str], header: list[str]) -> ParsedRow:
        def col(name: str) -> str:
            try:
                i = header.index(name)
            except ValueError:
                return ""
            return raw[i].strip() if i < len(raw) else ""

        def to_decimal(s: str) -> Decimal:
            cleaned = s.replace("$", "").replace(",", "").strip()
            if cleaned in ("", "-"):
                return Decimal("0")
            return Decimal(cleaned)

        date_s = col("Date")
        action_s = col("Action")
        symbol = col("Symbol")
        qty_s = col("Quantity")
        price_s = col("Price")
        fee_s = col("Fees & Comm") or col("Fee") or "0"

        # Dividend-type rows: surface as DIVIDEND so the import service
        # rejects them with the standard `dividend_actions_not_supported`
        # error rather than silently importing junk.
        if "Dividend" in action_s or "Cash In Lieu" in action_s:
            return ParsedRow(
                row_index=row_index,
                action=ACTION_DIVIDEND,
                symbol=symbol,
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=date.today(),
                currency="USD",
                raw_row=dict(zip(header, raw, strict=False)),
                error="dividend_actions_not_supported",
            )

        action = _ACTION_MAP.get(action_s, "")
        if not action:
            return ParsedRow(
                row_index=row_index,
                action=action_s,
                symbol=symbol,
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=date.today(),
                currency="USD",
                raw_row=dict(zip(header, raw, strict=False)),
                error="invalid_action",
            )

        trade_date = date.today()
        err: str | None = None
        try:
            trade_date = datetime.strptime(date_s, "%m/%d/%Y").date()  # noqa: DTZ007
        except ValueError:
            try:
                trade_date = datetime.strptime(date_s, "%Y-%m-%d").date()  # noqa: DTZ007
            except ValueError:
                err = "invalid_trade_date"

        qty = Decimal("0")
        price = Decimal("0")
        fee = Decimal("0")
        if err is None:
            try:
                qty = to_decimal(qty_s)
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
            fee = to_decimal(fee_s)
        except InvalidOperation:
            fee = Decimal("0")

        if err is None and not symbol:
            err = "missing_symbol"

        return ParsedRow(
            row_index=row_index,
            action=action,
            symbol=symbol.upper(),
            market=None,  # US exchange routing inferred at service layer
            quantity=qty,
            price=price,
            fee=fee,
            tax=Decimal("0"),  # Schwab doesn't surface SEC fees as a separate column on this export
            trade_date=trade_date,
            note=col("Description") or None,
            currency="USD",
            raw_row=dict(zip(header, raw, strict=False)),
            error=err,
        )


__all__ = ["SchwabParser"]
