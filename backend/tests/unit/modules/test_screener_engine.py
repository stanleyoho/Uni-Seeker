from datetime import date
from decimal import Decimal

from app.models.enums import Market
from app.models.price import StockPrice
from app.modules.indicators import create_default_registry
from app.modules.screener.conditions import Condition, ConditionGroup
from app.modules.screener.engine import ScreenerEngine


def _make_prices(symbol: str, closes: list[float]) -> list[StockPrice]:
    return [
        StockPrice(
            symbol=symbol,
            market=Market.TW_TWSE,
            date=date(2026, 4, i + 1),
            open=Decimal(str(c - 1)),
            high=Decimal(str(c + 2)),
            low=Decimal(str(c - 2)),
            close=Decimal(str(c)),
            volume=10_000_000,
        )
        for i, c in enumerate(closes)
    ]


def test_screen_finds_matching_stocks() -> None:
    engine = ScreenerEngine(registry=create_default_registry())
    rising = _make_prices("RISE.TW", [float(100 + i) for i in range(20)])
    falling = _make_prices("FALL.TW", [float(100 - i) for i in range(20)])
    conditions = ConditionGroup(operator="AND", rules=[
        Condition(indicator="RSI", params={"period": 14}, op="<", value=30),
    ])
    results = engine.screen({"RISE.TW": rising, "FALL.TW": falling}, conditions)
    symbols = [r.symbol for r in results]
    assert "FALL.TW" in symbols
    assert "RISE.TW" not in symbols


def test_screen_result_includes_indicator_values() -> None:
    engine = ScreenerEngine(registry=create_default_registry())
    prices = _make_prices("TEST.TW", [float(100 - i) for i in range(20)])
    conditions = ConditionGroup(operator="AND", rules=[
        Condition(indicator="RSI", params={"period": 14}, op="<", value=50),
    ])
    results = engine.screen({"TEST.TW": prices}, conditions)
    assert len(results) == 1
    assert "RSI" in results[0].indicator_values


def test_screen_empty_when_no_match() -> None:
    engine = ScreenerEngine(registry=create_default_registry())
    rising = _make_prices("RISE.TW", [float(100 + i) for i in range(20)])
    conditions = ConditionGroup(operator="AND", rules=[
        Condition(indicator="RSI", params={"period": 14}, op="<", value=5),
    ])
    assert engine.screen({"RISE.TW": rising}, conditions) == []


def test_screen_sort_by_indicator() -> None:
    engine = ScreenerEngine(registry=create_default_registry())
    stock_a = _make_prices("A.TW", [float(100 - i * 2) for i in range(20)])
    stock_b = _make_prices("B.TW", [float(100 - i) for i in range(20)])
    conditions = ConditionGroup(operator="AND", rules=[
        Condition(indicator="RSI", params={"period": 14}, op="<", value=50),
    ])
    results = engine.screen(
        {"A.TW": stock_a, "B.TW": stock_b},
        conditions,
        sort_by="RSI",
        sort_order="asc",
    )
    assert len(results) == 2
    assert results[0].indicator_values["RSI"] <= results[1].indicator_values["RSI"]
