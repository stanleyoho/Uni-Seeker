"""富邦證券 (Fubon) CSV adapter.

Assumed format::

    日期,代號,名稱,委託類別,股數,單價,手續費,證交稅
    2026/04/15,2330,台積電,B,1000,580,150,0
    2026/04/16,2454,聯發科,S,200,1000,90,300

Fubon's monthly statement is similar in spirit to Yuanta's but uses
shorter headers and the B/S action codes (買/賣 first letter Anglicised).
Date format is the same YYYY/MM/DD slash style.

Real-format caveat: Fubon offers multiple export variants (新銀世代 vs.
e01 vs. legacy ID). Stanley should sample-check a real export — see
report. We accept the most common 4-col 委託類別 form.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_SELL,
    ParsedRow,
)

_FUBON_MARKERS = ("日期", "代號", "委託類別")


_ACTION_MAP = {
    "B": ACTION_BUY,
    "買": ACTION_BUY,
    "買進": ACTION_BUY,
    "S": ACTION_SELL,
    "賣": ACTION_SELL,
    "賣出": ACTION_SELL,
}


class FubonParser:
    """富邦證券 CSV adapter."""

    BROKER_KEY = "fubon"
    DISPLAY_NAME = "富邦證券"
    EXPECTED_HEADERS: tuple[str, ...] = _FUBON_MARKERS

    def can_handle(self, csv_content: str) -> bool:
        head = "\n".join(csv_content.splitlines()[:5])
        # Yuanta also has "日期" / "代號"-ish columns; we disambiguate
        # by checking 委託類別 (Yuanta uses 交易類別). The two diverge
        # exactly on this column.
        if "交易類別" in head:
            return False
        return all(marker in head for marker in _FUBON_MARKERS)

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader, None)
        if not header or not all(m in ",".join(header) for m in _FUBON_MARKERS):
            raise ValueError("invalid_csv_format: missing Fubon header")
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

        date_s = col("日期")
        symbol = col("代號")
        action_s = col("委託類別")
        qty_s = col("股數")
        price_s = col("單價") or col("價格")
        fee_s = col("手續費") or "0"
        tax_s = col("證交稅") or col("交易稅") or "0"

        action = _ACTION_MAP.get(action_s, "")
        if not action:
            return ParsedRow(
                row_index=row_index,
                action=action_s,
                symbol=symbol,
                market="TW_TWSE",
                quantity=Decimal("0"),
                price=Decimal("0"),
                fee=Decimal("0"),
                tax=Decimal("0"),
                trade_date=datetime.today().date(),
                currency="TWD",
                raw_row=dict(zip(header, raw, strict=False)),
                error="invalid_action",
            )

        trade_date = datetime.today().date()
        err: str | None = None
        try:
            normalised = date_s.replace("-", "/")
            parts = normalised.split("/")
            if len(parts) == 3 and len(parts[0]) <= 3:
                parts[0] = str(int(parts[0]) + 1911)
            trade_date = datetime.strptime("/".join(parts), "%Y/%m/%d").date()
        except (ValueError, IndexError):
            err = "invalid_trade_date"

        qty = Decimal("0")
        if err is None:
            try:
                qty = Decimal(qty_s.replace(",", ""))
                if qty <= Decimal("0"):
                    err = "invalid_quantity"
            except InvalidOperation:
                err = "invalid_quantity"

        price = Decimal("0")
        if err is None:
            try:
                price = Decimal(price_s.replace(",", ""))
                if price <= Decimal("0"):
                    err = "invalid_price"
            except InvalidOperation:
                err = "invalid_price"

        try:
            fee = Decimal(fee_s.replace(",", "")) if fee_s else Decimal("0")
        except InvalidOperation:
            fee = Decimal("0")
        try:
            tax = Decimal(tax_s.replace(",", "")) if tax_s else Decimal("0")
        except InvalidOperation:
            tax = Decimal("0")

        if err is None and not symbol:
            err = "missing_symbol"

        return ParsedRow(
            row_index=row_index,
            action=action,
            symbol=symbol,
            market="TW_TWSE",
            quantity=qty,
            price=price,
            fee=fee,
            tax=tax,
            trade_date=trade_date,
            currency="TWD",
            raw_row=dict(zip(header, raw, strict=False)),
            error=err,
        )


__all__ = ["FubonParser"]
