"""元大證券 (Yuanta) 月對帳單 CSV adapter.

Assumed format (CN headers, Big5 or UTF-8 BOM)::

    交易日期,股票代號,股票名稱,交易類別,股數,價格,手續費,交易稅
    2026/04/15,2330,台積電,買進,1000,580,150,0
    2026/04/16,2330,台積電,賣出,500,600,90,180

Date format: ``YYYY/MM/DD`` (slashes — Yuanta's monthly statement
convention). The /holdings/imports endpoint already decodes the body
as UTF-8-with-BOM; if the user uploaded raw Big5, the API layer 422s
before we get here.

Action vocabulary:
    買進 → BUY
    賣出 → SELL
    現增 / 配股 → ignored (not in trade log scope yet)

Real-format caveat: Yuanta exports vary by account type (現股 vs.
信用 vs. 零股). Headers here cover 現股. Stanley should validate
against a real export — see report for the exact list of columns
to confirm.
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

# Header keywords we look for during auto-detection. Yuanta files
# always start with ``交易日期`` and ``股票代號`` in the first row.
_YUANTA_MARKERS = ("交易日期", "股票代號", "交易類別")


_ACTION_MAP = {
    "買進": ACTION_BUY,
    "買": ACTION_BUY,
    "B": ACTION_BUY,
    "賣出": ACTION_SELL,
    "賣": ACTION_SELL,
    "S": ACTION_SELL,
}


class YuantaParser:
    """元大證券 CSV adapter."""

    BROKER_KEY = "yuanta"
    DISPLAY_NAME = "元大證券"
    EXPECTED_HEADERS: tuple[str, ...] = _YUANTA_MARKERS

    def can_handle(self, csv_content: str) -> bool:
        head = "\n".join(csv_content.splitlines()[:5])
        # All three markers in the header — keeps detection from
        # firing on the broader Fubon shape (which also has 股數 etc.).
        return all(marker in head for marker in _YUANTA_MARKERS)

    def parse(self, csv_content: str) -> list[ParsedRow]:
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader, None)
        if not header or not all(m in (",".join(header)) for m in _YUANTA_MARKERS):
            raise ValueError("invalid_csv_format: missing Yuanta header")
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

        date_s = col("交易日期")
        symbol = col("股票代號")
        action_s = col("交易類別")
        qty_s = col("股數")
        price_s = col("價格") or col("成交價")
        fee_s = col("手續費") or "0"
        tax_s = col("交易稅") or "0"

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

        # Date — Yuanta uses YYYY/MM/DD. ROC year ("民國") sometimes
        # appears in older exports; we map 1xx → 2xxx defensively.
        trade_date = datetime.today().date()
        err: str | None = None
        try:
            normalised = date_s.replace("-", "/")
            parts = normalised.split("/")
            if len(parts) == 3 and len(parts[0]) <= 3:
                # ROC year — 113 → 2024
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
            market="TW_TWSE",  # Yuanta primary market; TPEx flagged separately in real files
            quantity=qty,
            price=price,
            fee=fee,
            tax=tax,
            trade_date=trade_date,
            note=col("備註") or None,
            currency="TWD",
            raw_row=dict(zip(header, raw, strict=False)),
            error=err,
        )


__all__ = ["YuantaParser"]
