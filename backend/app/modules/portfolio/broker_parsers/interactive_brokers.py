"""Interactive Brokers Flex Statement adapter.

IB Flex Statement Reference (CSV variant) — multi-section file where
each section is led by a magic key in column A. The Trades section we
care about looks like::

    Statement,Header,...
    ...
    Trades,Header,DataDiscriminator,Asset Category,Symbol,Date/Time,Quantity,T. Price,Comm/Fee,...
    Trades,Data,Order,Stocks,NVDA,2026-04-15;09:35:11,100,500.00,-1.00,...
    Trades,Data,Order,Stocks,NVDA,2026-04-16;10:00:00,-50,510.00,-1.00,...

Key observations:

* The "Trades" subsection header is repeated for every data row by
  IB design (every section in a Flex file is self-describing).
* Quantity carries the sign — positive = BUY, negative = SELL.
* Commission column is signed negative when IB charged the user
  (we strip the sign before storing fee).
* "Date/Time" combines date + time separated by ``;`` (occasionally
  a comma — defensive split).
* Currency / Market: Flex includes a "Currency" column but auto-detect
  works fine because IB customers are overwhelmingly USD/US equities.
  Adapter defaults to USD; service can override via Market enum.

We tolerate cosmetic variation: trailing commas, extra columns IB adds
over time, blank rows between sections. Anything not matching a known
Trades line is silently skipped at parse time.

Real-format caveat: this adapter is built from spec — Stanley should
verify against an actual IB Flex export before locking down the
detection heuristic.
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_type, datetime
from decimal import Decimal, InvalidOperation

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_SELL,
    ParsedRow,
)


# Detection markers — any of these in the first ~20 lines flips
# can_handle() to True. We pick three signals because a Flex file
# usually carries all of them, but a heavily-customized export might
# strip the "Statement,Header" preamble.
_IB_MARKERS = (
    "Trades,Header,DataDiscriminator",
    "Statement,Header,Field Name",
    "Account Information,Header,",
)


class InteractiveBrokersParser:
    """IB Flex Statement CSV adapter."""

    BROKER_KEY = "interactive_brokers"
    DISPLAY_NAME = "Interactive Brokers (Flex Query)"
    EXPECTED_HEADERS: tuple[str, ...] = _IB_MARKERS

    def can_handle(self, csv_content: str) -> bool:
        head = "\n".join(csv_content.splitlines()[:25])
        return any(marker in head for marker in _IB_MARKERS)

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        trade_header: list[str] | None = None
        rows: list[ParsedRow] = []
        for idx, raw in enumerate(reader, start=1):
            if not raw:
                continue
            section = raw[0].strip() if raw else ""
            if section != "Trades":
                continue
            kind = raw[1].strip() if len(raw) > 1 else ""
            if kind == "Header":
                # IB sometimes emits multiple Trades,Header lines (one
                # per section). We keep the latest so the column index
                # lookup below stays valid.
                trade_header = [c.strip() for c in raw]
                continue
            if kind != "Data" or trade_header is None:
                continue
            parsed = self._parse_trade_row(idx, raw, trade_header)
            if parsed is not None:
                rows.append(parsed)
        if not rows:
            # No header / no data — surface as fatal so the API layer
            # 422s instead of pretending the file was empty.
            raise ValueError("invalid_csv_format: no IB trades section found")
        return rows

    def _parse_trade_row(
        self,
        row_index: int,
        raw: list[str],
        header: list[str],
    ) -> ParsedRow | None:
        def col(name: str) -> str:
            try:
                i = header.index(name)
            except ValueError:
                return ""
            return raw[i].strip() if i < len(raw) else ""

        # IB column names. The "Date/Time" column sometimes appears as
        # "TradeDate" in flex queries that omit timestamps — accept both.
        symbol = col("Symbol")
        date_s = col("Date/Time") or col("TradeDate") or col("Date")
        qty_s = col("Quantity")
        price_s = col("T. Price") or col("TradePrice")
        comm_s = col("Comm/Fee") or col("IBCommission")
        tax_s = col("Tax") or "0"
        currency = col("Currency") or "USD"

        if not symbol or not date_s or not qty_s or not price_s:
            # Not a stock trade row (could be option / currency / cash
            # statement subtype) — silently skip rather than error so
            # the file as a whole still imports.
            return None

        # Date parse — IB ships ``YYYY-MM-DD;HH:MM:SS`` (semicolon).
        # Some flex profiles use a single space. We strip the time
        # because the trade log is daily granularity.
        date_part = date_s.split(";")[0].split(" ")[0]
        try:
            trade_date: date_type = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            return ParsedRow(
                row_index=row_index,
                action=ACTION_BUY,
                symbol=symbol.upper(),
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=date_type.today(),
                currency=currency,
                error="invalid_trade_date",
            )

        # Quantity carries the sign. Decimal handles a leading minus
        # naturally but trips on "1,000" — strip thousands separators
        # IB occasionally inserts.
        qty_clean = qty_s.replace(",", "")
        try:
            qty_signed = Decimal(qty_clean)
        except InvalidOperation:
            return ParsedRow(
                row_index=row_index,
                action=ACTION_BUY,
                symbol=symbol.upper(),
                market=None,
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=trade_date,
                currency=currency,
                error="invalid_quantity",
            )

        action = ACTION_SELL if qty_signed < 0 else ACTION_BUY
        qty = abs(qty_signed)

        try:
            price = Decimal(price_s.replace(",", ""))
        except InvalidOperation:
            return ParsedRow(
                row_index=row_index,
                action=action,
                symbol=symbol.upper(),
                market=None,
                quantity=qty,
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=trade_date,
                currency=currency,
                error="invalid_price",
            )

        # Commission is signed negative when charged. Use abs() so we
        # store a positive fee on `portfolio_trades.fee`.
        try:
            fee = abs(Decimal(comm_s.replace(",", ""))) if comm_s else Decimal("0")
        except InvalidOperation:
            fee = Decimal("0")
        try:
            tax = abs(Decimal(tax_s.replace(",", ""))) if tax_s else Decimal("0")
        except InvalidOperation:
            tax = Decimal("0")

        if qty <= Decimal("0"):
            err = "invalid_quantity"
        elif price <= Decimal("0"):
            err = "invalid_price"
        else:
            err = None

        return ParsedRow(
            row_index=row_index,
            action=action,
            symbol=symbol.upper(),
            market=None,  # service infers US_NYSE/US_NASDAQ from symbol if needed
            quantity=qty,
            price=price,
            fee=fee,
            tax=tax,
            trade_date=trade_date,
            note=f"IB Order {col('OrderID') or col('TradeID') or ''}".strip() or None,
            currency=currency or "USD",
            raw_row={h: (raw[i] if i < len(raw) else "") for i, h in enumerate(header)},
            error=err,
        )


__all__ = ["InteractiveBrokersParser"]
