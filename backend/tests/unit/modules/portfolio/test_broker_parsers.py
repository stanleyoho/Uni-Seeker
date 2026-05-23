"""Unit tests — broker-specific CSV adapters (Round 10).

Pure-function tests against `app.modules.portfolio.broker_parsers.*`.
Each broker has its own fixture file under ./fixtures so the test
harness exercises a realistic shape (header, body, edge cases).

We cover:

* 5 broker parsers × ~5 cases each (basic parse, action mapping,
  decimal cleaning, dividend rejection, malformed input).
* Auto-detect: `detect_parser` picks the right adapter for each
  fixture, falls back to generic for the canonical Uni-Seeker shape,
  and never crosses streams.

No DB, no FastAPI — adapters are pure.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.portfolio.broker_parsers import (
    DEFAULT_PARSER_CLASSES,
    FidelityParser,
    FubonParser,
    GenericCsvParser,
    InteractiveBrokersParser,
    SchwabParser,
    YuantaParser,
    detect_parser,
)
from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_DIVIDEND,
    ACTION_SELL,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ── Interactive Brokers ────────────────────────────────────────────────


class TestInteractiveBrokers:
    def test_basic_parse(self) -> None:
        parser = InteractiveBrokersParser()
        rows = parser.parse(_load("sample_ib.csv"))
        assert len(rows) == 3
        first = rows[0]
        assert first.action == ACTION_BUY
        assert first.symbol == "NVDA"
        assert first.quantity == Decimal("100")
        assert first.price == Decimal("500.00")
        assert first.trade_date == date(2026, 4, 15)
        assert first.currency == "USD"

    def test_negative_quantity_maps_to_sell(self) -> None:
        parser = InteractiveBrokersParser()
        rows = parser.parse(_load("sample_ib.csv"))
        sell = rows[1]
        assert sell.action == ACTION_SELL
        assert sell.quantity == Decimal("50")  # abs()

    def test_commission_stripped_of_sign(self) -> None:
        parser = InteractiveBrokersParser()
        rows = parser.parse(_load("sample_ib.csv"))
        assert rows[0].fee == Decimal("1.00")  # -1.00 → 1.00

    def test_can_handle_ib_markers(self) -> None:
        parser = InteractiveBrokersParser()
        assert parser.can_handle(_load("sample_ib.csv")) is True

    def test_can_handle_rejects_yuanta(self) -> None:
        parser = InteractiveBrokersParser()
        assert parser.can_handle(_load("sample_yuanta.csv")) is False

    def test_empty_trades_raises(self) -> None:
        parser = InteractiveBrokersParser()
        with pytest.raises(ValueError):
            parser.parse("Statement,Header,Field Name,Field Value\n")


# ── Yuanta ────────────────────────────────────────────────────────────


class TestYuanta:
    def test_basic_parse(self) -> None:
        parser = YuantaParser()
        rows = parser.parse(_load("sample_yuanta.csv"))
        assert len(rows) == 3
        first = rows[0]
        assert first.symbol == "2330"
        assert first.action == ACTION_BUY
        assert first.quantity == Decimal("1000")
        assert first.price == Decimal("580")
        assert first.market == "TW_TWSE"
        assert first.currency == "TWD"
        assert first.trade_date == date(2026, 4, 15)

    def test_sell_action_mapping(self) -> None:
        parser = YuantaParser()
        rows = parser.parse(_load("sample_yuanta.csv"))
        assert rows[2].action == ACTION_SELL
        assert rows[2].quantity == Decimal("500")

    def test_can_handle_yuanta_markers(self) -> None:
        parser = YuantaParser()
        assert parser.can_handle(_load("sample_yuanta.csv")) is True

    def test_can_handle_rejects_fubon(self) -> None:
        parser = YuantaParser()
        assert parser.can_handle(_load("sample_fubon.csv")) is False

    def test_invalid_action_flagged(self) -> None:
        parser = YuantaParser()
        body = "交易日期,股票代號,股票名稱,交易類別,股數,價格,手續費,交易稅\n2026/04/15,2330,台積電,UNKNOWN,1000,580,150,0\n"
        rows = parser.parse(body)
        assert rows[0].error == "invalid_action"


# ── Fubon ─────────────────────────────────────────────────────────────


class TestFubon:
    def test_basic_parse(self) -> None:
        parser = FubonParser()
        rows = parser.parse(_load("sample_fubon.csv"))
        assert len(rows) == 3
        assert rows[0].action == ACTION_BUY
        assert rows[1].action == ACTION_SELL
        assert rows[0].symbol == "2330"
        assert rows[0].market == "TW_TWSE"
        assert rows[0].quantity == Decimal("1000")

    def test_b_s_action_mapping(self) -> None:
        parser = FubonParser()
        rows = parser.parse(_load("sample_fubon.csv"))
        assert rows[0].action == ACTION_BUY  # "B"
        assert rows[1].action == ACTION_SELL  # "S"

    def test_can_handle_fubon_markers(self) -> None:
        parser = FubonParser()
        assert parser.can_handle(_load("sample_fubon.csv")) is True

    def test_can_handle_rejects_yuanta(self) -> None:
        parser = FubonParser()
        # Yuanta has 交易類別; Fubon parser should reject it.
        assert parser.can_handle(_load("sample_yuanta.csv")) is False

    def test_tax_parsed(self) -> None:
        parser = FubonParser()
        rows = parser.parse(_load("sample_fubon.csv"))
        # Row 2 is a SELL with 證交稅=300
        assert rows[1].tax == Decimal("300")


# ── Schwab ────────────────────────────────────────────────────────────


class TestSchwab:
    def test_basic_parse(self) -> None:
        parser = SchwabParser()
        rows = parser.parse(_load("sample_schwab.csv"))
        # 4 rows in file (3 trades + 1 dividend rejected)
        assert len(rows) == 4
        assert rows[0].symbol == "NVDA"
        assert rows[0].action == ACTION_BUY
        assert rows[0].quantity == Decimal("100")
        assert rows[0].price == Decimal("500.00")

    def test_dollar_sign_stripped(self) -> None:
        parser = SchwabParser()
        rows = parser.parse(_load("sample_schwab.csv"))
        assert rows[0].fee == Decimal("0.00")
        # row 2: sell
        assert rows[1].action == ACTION_SELL

    def test_dividend_action_rejected(self) -> None:
        parser = SchwabParser()
        rows = parser.parse(_load("sample_schwab.csv"))
        # The "Cash Dividend" row should be tagged as dividend-rejection.
        div_row = next(r for r in rows if "Dividend" in (r.raw_row or {}).get("Action", ""))
        assert div_row.error == "dividend_actions_not_supported"
        assert div_row.action == ACTION_DIVIDEND

    def test_us_date_parsing(self) -> None:
        parser = SchwabParser()
        rows = parser.parse(_load("sample_schwab.csv"))
        # 04/15/2026 → date(2026, 4, 15)
        assert rows[0].trade_date == date(2026, 4, 15)

    def test_can_handle_schwab_markers(self) -> None:
        parser = SchwabParser()
        assert parser.can_handle(_load("sample_schwab.csv")) is True


# ── Fidelity ──────────────────────────────────────────────────────────


class TestFidelity:
    def test_basic_parse(self) -> None:
        parser = FidelityParser()
        rows = parser.parse(_load("sample_fidelity.csv"))
        assert len(rows) == 4

    def test_you_bought_maps_to_buy(self) -> None:
        parser = FidelityParser()
        rows = parser.parse(_load("sample_fidelity.csv"))
        assert rows[0].action == ACTION_BUY
        assert rows[0].symbol == "NVDA"

    def test_you_sold_maps_to_sell(self) -> None:
        parser = FidelityParser()
        rows = parser.parse(_load("sample_fidelity.csv"))
        assert rows[1].action == ACTION_SELL

    def test_dividend_received_rejected(self) -> None:
        parser = FidelityParser()
        rows = parser.parse(_load("sample_fidelity.csv"))
        div = rows[-1]
        assert div.action == ACTION_DIVIDEND
        assert div.error == "dividend_actions_not_supported"

    def test_can_handle_fidelity_markers(self) -> None:
        parser = FidelityParser()
        assert parser.can_handle(_load("sample_fidelity.csv")) is True


# ── Generic (Y2 fallback) ─────────────────────────────────────────────


class TestGeneric:
    def test_basic_parse(self) -> None:
        parser = GenericCsvParser()
        body = (
            "trade_date,action,symbol,market,quantity,price,fee,tax,note\n"
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,\n"
            "2026-05-02,SELL,2330,TW_TWSE,5,600,0,0,\n"
        )
        rows = parser.parse(body)
        assert len(rows) == 2
        assert rows[0].symbol == "2330"
        assert rows[0].action == ACTION_BUY
        assert rows[1].action == ACTION_SELL

    def test_dividend_row_flagged(self) -> None:
        parser = GenericCsvParser()
        body = (
            "trade_date,action,symbol,market,quantity,price,fee,tax,note\n"
            "2026-05-01,DIVIDEND,2330,TW_TWSE,10,5,0,0,\n"
        )
        rows = parser.parse(body)
        assert rows[0].error == "dividend_actions_not_supported"

    def test_missing_header_raises(self) -> None:
        parser = GenericCsvParser()
        with pytest.raises(ValueError):
            parser.parse("date,foo,bar\n2026-05-01,BUY,X\n")

    def test_can_handle_canonical_header(self) -> None:
        parser = GenericCsvParser()
        assert parser.can_handle(
            "trade_date,action,symbol,market,quantity,price,fee,tax,note\n"
        ) is True


# ── Auto-detect ───────────────────────────────────────────────────────


class TestAutoDetect:
    def test_detect_ib(self) -> None:
        p = detect_parser(_load("sample_ib.csv"))
        assert isinstance(p, InteractiveBrokersParser)

    def test_detect_yuanta(self) -> None:
        p = detect_parser(_load("sample_yuanta.csv"))
        assert isinstance(p, YuantaParser)

    def test_detect_fubon(self) -> None:
        p = detect_parser(_load("sample_fubon.csv"))
        assert isinstance(p, FubonParser)

    def test_detect_schwab(self) -> None:
        p = detect_parser(_load("sample_schwab.csv"))
        assert isinstance(p, SchwabParser)

    def test_detect_fidelity(self) -> None:
        p = detect_parser(_load("sample_fidelity.csv"))
        assert isinstance(p, FidelityParser)

    def test_detect_falls_back_to_generic(self) -> None:
        body = (
            "trade_date,action,symbol,market,quantity,price,fee,tax,note\n"
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,\n"
        )
        p = detect_parser(body)
        assert isinstance(p, GenericCsvParser)

    def test_registry_order(self) -> None:
        # Broker-specific first, generic last.
        assert DEFAULT_PARSER_CLASSES[-1] is GenericCsvParser
        assert InteractiveBrokersParser in DEFAULT_PARSER_CLASSES
