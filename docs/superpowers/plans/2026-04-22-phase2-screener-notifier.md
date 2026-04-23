# Phase 2: Screener + Notifier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build stock screener (indicator-based filtering + industry PE analysis) and Telegram notification system with scheduled alerts.

**Architecture:** Screener uses a condition DSL (JSON) evaluated against pre-computed indicators. Industry screener fetches PE/PB data from TWSE BWIBBU_ALL. Notifier uses python-telegram-bot with APScheduler for scheduled delivery.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, python-telegram-bot, APScheduler

---

## File Structure (Phase 2 additions)

```
backend/
├── app/
│   ├── models/
│   │   ├── valuation.py          # PE/PB/yield data model
│   │   ├── screener.py           # SavedScreen model
│   │   └── notification.py       # NotificationRule + NotificationLog models
│   ├── schemas/
│   │   ├── screener.py           # Screener request/response schemas
│   │   └── notification.py       # Notification schemas
│   ├── api/v1/
│   │   ├── screener.py           # Screener endpoints
│   │   └── notifications.py      # Notification endpoints
│   ├── modules/
│   │   ├── screener/
│   │   │   ├── __init__.py
│   │   │   ├── conditions.py     # Condition DSL parser + evaluator
│   │   │   ├── engine.py         # ScreenerEngine (runs conditions against stocks)
│   │   │   └── industry.py       # IndustryScreener (PE Z-Score analysis)
│   │   ├── valuation/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # ValuationProvider protocol
│   │   │   └── twse_valuation.py # TWSE BWIBBU_ALL provider
│   │   └── notifier/
│   │       ├── __init__.py
│   │       ├── base.py           # NotificationChannel protocol
│   │       ├── telegram.py       # Telegram implementation
│   │       ├── templates.py      # Message templates
│   │       └── scheduler.py      # APScheduler notification scheduler
│   └── services/
│       └── __init__.py
├── tests/
│   ├── unit/modules/
│   │   ├── test_conditions.py
│   │   ├── test_screener_engine.py
│   │   ├── test_industry_screener.py
│   │   ├── test_twse_valuation.py
│   │   ├── test_telegram_notifier.py
│   │   ├── test_notification_templates.py
│   │   └── test_notification_scheduler.py
│   └── integration/
│       ├── test_screener_api.py
│       └── test_notifications_api.py
```

---

## Task 1: Valuation Data Model + TWSE BWIBBU Provider

**Files:**
- Create: `backend/app/models/valuation.py`
- Create: `backend/app/modules/valuation/__init__.py`
- Create: `backend/app/modules/valuation/base.py`
- Create: `backend/app/modules/valuation/twse_valuation.py`
- Create: `backend/tests/unit/modules/test_twse_valuation.py`
- Modify: `backend/app/models/__init__.py`

### Step 1: Write failing test

- [ ] **Step 1.1: Create test_twse_valuation.py**

```python
# tests/unit/modules/test_twse_valuation.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.modules.valuation.base import ValuationData, ValuationProvider
from app.modules.valuation.twse_valuation import TWSEValuationProvider

BWIBBU_SAMPLE = [
    {
        "Code": "2330",
        "Name": "台積電",
        "PEratio": "22.50",
        "DividendYield": "1.80",
        "PBratio": "5.60",
    },
    {
        "Code": "2317",
        "Name": "鴻海",
        "PEratio": "12.47",
        "DividendYield": "6.52",
        "PBratio": "0.69",
    },
    {
        "Code": "1101",
        "Name": "台泥",
        "PEratio": "",
        "DividendYield": "3.23",
        "PBratio": "0.82",
    },
]


def test_provider_is_valuation_provider() -> None:
    provider = TWSEValuationProvider(client=AsyncMock())
    assert isinstance(provider, ValuationProvider)


async def test_fetch_all_valuations() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = BWIBBU_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSEValuationProvider(client=mock_client)
    data = await provider.fetch_valuations()

    assert len(data) == 3
    assert data[0].symbol == "2330.TW"
    assert data[0].pe_ratio == Decimal("22.50")
    assert data[0].pb_ratio == Decimal("5.60")
    assert data[0].dividend_yield == Decimal("1.80")


async def test_empty_pe_is_none() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = BWIBBU_SAMPLE
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSEValuationProvider(client=mock_client)
    data = await provider.fetch_valuations()

    tai_ni = data[2]
    assert tai_ni.symbol == "1101.TW"
    assert tai_ni.pe_ratio is None
    assert tai_ni.dividend_yield == Decimal("3.23")


async def test_fetch_empty_response() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    provider = TWSEValuationProvider(client=mock_client)
    assert await provider.fetch_valuations() == []
```

- [ ] **Step 1.2: Run test — verify FAIL**

- [ ] **Step 1.3: Implement base.py**

```python
# app/modules/valuation/base.py
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ValuationData:
    symbol: str
    name: str
    date: date
    pe_ratio: Decimal | None
    pb_ratio: Decimal | None
    dividend_yield: Decimal | None
    industry: str = ""


@runtime_checkable
class ValuationProvider(Protocol):
    async def fetch_valuations(self) -> list[ValuationData]: ...
```

- [ ] **Step 1.4: Implement twse_valuation.py**

```python
# app/modules/valuation/twse_valuation.py
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.valuation.base import ValuationData

logger = structlog.get_logger()

BWIBBU_ALL = "/exchangeReport/BWIBBU_ALL"


class TWSEValuationProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://openapi.twse.com.tw/v1") -> None:
        self._client = client
        self._base_url = base_url

    async def fetch_valuations(self) -> list[ValuationData]:
        url = f"{self._base_url}{BWIBBU_ALL}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw: list[dict[str, str]] = response.json()

        results: list[ValuationData] = []
        today = date.today()

        for record in raw:
            code = record.get("Code", "")
            pe_str = record.get("PEratio", "").strip()
            pb_str = record.get("PBratio", "").strip()
            dy_str = record.get("DividendYield", "").strip()

            try:
                pe = Decimal(pe_str) if pe_str else None
            except InvalidOperation:
                pe = None
            try:
                pb = Decimal(pb_str) if pb_str else None
            except InvalidOperation:
                pb = None
            try:
                dy = Decimal(dy_str) if dy_str else None
            except InvalidOperation:
                dy = None

            results.append(
                ValuationData(
                    symbol=f"{code}.TW",
                    name=record.get("Name", ""),
                    date=today,
                    pe_ratio=pe,
                    pb_ratio=pb,
                    dividend_yield=dy,
                )
            )

        return results
```

- [ ] **Step 1.5: Create valuation model**

```python
# app/models/valuation.py
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StockValuation(Base):
    __tablename__ = "stock_valuations"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_valuation_symbol_date"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    pb_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=None)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)
    industry: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
```

- [ ] **Step 1.6: Run tests — verify PASS**
- [ ] **Step 1.7: Commit**: `feat: add ValuationProvider protocol and TWSE BWIBBU provider`

---

## Task 2: Screener Condition DSL + Engine

**Files:**
- Create: `backend/app/modules/screener/__init__.py`
- Create: `backend/app/modules/screener/conditions.py`
- Create: `backend/app/modules/screener/engine.py`
- Create: `backend/tests/unit/modules/test_conditions.py`
- Create: `backend/tests/unit/modules/test_screener_engine.py`

### Step 1: Condition DSL

- [ ] **Step 1.1: Write test_conditions.py**

```python
# tests/unit/modules/test_conditions.py
from app.modules.screener.conditions import Condition, ConditionGroup, evaluate_condition


def test_less_than() -> None:
    c = Condition(indicator="RSI", params={"period": 14}, op="<", value=30)
    assert evaluate_condition(c, {"RSI": 25.0}) is True
    assert evaluate_condition(c, {"RSI": 35.0}) is False


def test_greater_than() -> None:
    c = Condition(indicator="RSI", params={}, op=">", value=70)
    assert evaluate_condition(c, {"RSI": 75.0}) is True
    assert evaluate_condition(c, {"RSI": 65.0}) is False


def test_between() -> None:
    c = Condition(indicator="RSI", params={}, op="between", value=[30, 70])
    assert evaluate_condition(c, {"RSI": 50.0}) is True
    assert evaluate_condition(c, {"RSI": 25.0}) is False
    assert evaluate_condition(c, {"RSI": 75.0}) is False


def test_equal() -> None:
    c = Condition(indicator="PE", params={}, op="==", value=15.0)
    assert evaluate_condition(c, {"PE": 15.0}) is True
    assert evaluate_condition(c, {"PE": 16.0}) is False


def test_missing_indicator_returns_false() -> None:
    c = Condition(indicator="RSI", params={}, op="<", value=30)
    assert evaluate_condition(c, {}) is False


def test_condition_group_and() -> None:
    group = ConditionGroup(
        operator="AND",
        rules=[
            Condition(indicator="RSI", params={}, op="<", value=30),
            Condition(indicator="KD_K", params={}, op="<", value=20),
        ],
    )
    assert group.evaluate({"RSI": 25.0, "KD_K": 15.0}) is True
    assert group.evaluate({"RSI": 25.0, "KD_K": 25.0}) is False


def test_condition_group_or() -> None:
    group = ConditionGroup(
        operator="OR",
        rules=[
            Condition(indicator="RSI", params={}, op="<", value=30),
            Condition(indicator="KD_K", params={}, op="<", value=20),
        ],
    )
    assert group.evaluate({"RSI": 25.0, "KD_K": 50.0}) is True
    assert group.evaluate({"RSI": 50.0, "KD_K": 50.0}) is False
```

- [ ] **Step 1.2: Implement conditions.py**

```python
# app/modules/screener/conditions.py
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Condition:
    indicator: str
    params: dict[str, Any]
    op: str  # <, >, <=, >=, ==, between
    value: Any


def evaluate_condition(condition: Condition, indicator_values: dict[str, float | None]) -> bool:
    actual = indicator_values.get(condition.indicator)
    if actual is None:
        return False

    match condition.op:
        case "<":
            return actual < condition.value
        case ">":
            return actual > condition.value
        case "<=":
            return actual <= condition.value
        case ">=":
            return actual >= condition.value
        case "==":
            return actual == condition.value
        case "between":
            low, high = condition.value
            return low <= actual <= high
        case _:
            return False


@dataclass
class ConditionGroup:
    operator: str  # AND or OR
    rules: list[Condition] = field(default_factory=list)

    def evaluate(self, indicator_values: dict[str, float | None]) -> bool:
        if self.operator == "AND":
            return all(evaluate_condition(r, indicator_values) for r in self.rules)
        return any(evaluate_condition(r, indicator_values) for r in self.rules)
```

- [ ] **Step 1.3: Run tests — verify PASS**
- [ ] **Step 1.4: Commit**: `feat: add screener condition DSL with AND/OR groups`

### Step 2: Screener Engine

- [ ] **Step 2.1: Write test_screener_engine.py**

```python
# tests/unit/modules/test_screener_engine.py
from datetime import date
from decimal import Decimal

from app.models.enums import Market
from app.models.price import StockPrice
from app.modules.indicators import create_default_registry
from app.modules.screener.conditions import Condition, ConditionGroup
from app.modules.screener.engine import ScreenerEngine, ScreenResult


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
    registry = create_default_registry()
    engine = ScreenerEngine(registry=registry)

    # Steadily rising = RSI near 100
    rising = _make_prices("RISE.TW", [float(100 + i) for i in range(20)])
    # Steadily falling = RSI near 0
    falling = _make_prices("FALL.TW", [float(100 - i) for i in range(20)])

    conditions = ConditionGroup(
        operator="AND",
        rules=[Condition(indicator="RSI", params={"period": 14}, op="<", value=30)],
    )

    results = engine.screen({"RISE.TW": rising, "FALL.TW": falling}, conditions)
    symbols = [r.symbol for r in results]
    assert "FALL.TW" in symbols
    assert "RISE.TW" not in symbols


def test_screen_result_includes_indicator_values() -> None:
    registry = create_default_registry()
    engine = ScreenerEngine(registry=registry)

    prices = _make_prices("TEST.TW", [float(100 - i) for i in range(20)])
    conditions = ConditionGroup(
        operator="AND",
        rules=[Condition(indicator="RSI", params={"period": 14}, op="<", value=50)],
    )

    results = engine.screen({"TEST.TW": prices}, conditions)
    assert len(results) == 1
    assert "RSI" in results[0].indicator_values


def test_screen_empty_when_no_match() -> None:
    registry = create_default_registry()
    engine = ScreenerEngine(registry=registry)

    rising = _make_prices("RISE.TW", [float(100 + i) for i in range(20)])
    conditions = ConditionGroup(
        operator="AND",
        rules=[Condition(indicator="RSI", params={"period": 14}, op="<", value=5)],
    )

    results = engine.screen({"RISE.TW": rising}, conditions)
    assert results == []


def test_screen_sort_by_indicator() -> None:
    registry = create_default_registry()
    engine = ScreenerEngine(registry=registry)

    stock_a = _make_prices("A.TW", [float(100 - i * 2) for i in range(20)])
    stock_b = _make_prices("B.TW", [float(100 - i) for i in range(20)])

    conditions = ConditionGroup(
        operator="AND",
        rules=[Condition(indicator="RSI", params={"period": 14}, op="<", value=50)],
    )

    results = engine.screen(
        {"A.TW": stock_a, "B.TW": stock_b},
        conditions,
        sort_by="RSI",
        sort_order="asc",
    )
    assert len(results) == 2
    assert results[0].indicator_values["RSI"] <= results[1].indicator_values["RSI"]
```

- [ ] **Step 2.2: Implement engine.py**

```python
# app/modules/screener/engine.py
from dataclasses import dataclass

from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.screener.conditions import ConditionGroup


@dataclass
class ScreenResult:
    symbol: str
    indicator_values: dict[str, float]


class ScreenerEngine:
    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry

    def screen(
        self,
        stocks_prices: dict[str, list[StockPrice]],
        conditions: ConditionGroup,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[ScreenResult]:
        results: list[ScreenResult] = []

        needed_indicators = {rule.indicator for rule in conditions.rules}

        for symbol, prices in stocks_prices.items():
            if not prices:
                continue

            closes = [float(p.close) for p in prices]
            highs = [float(p.high) for p in prices]
            lows = [float(p.low) for p in prices]
            volumes = [p.volume for p in prices]

            indicator_values: dict[str, float] = {}

            for ind_name in needed_indicators:
                # Map condition indicator names to registry names
                registry_name = ind_name.split("_")[0] if "_" in ind_name else ind_name
                try:
                    indicator = self._registry.get(registry_name)
                except KeyError:
                    continue

                params: dict[str, object] = {}
                # Find params from matching condition
                for rule in conditions.rules:
                    if rule.indicator == ind_name:
                        params = dict(rule.params)
                        break

                if registry_name == "KD":
                    params["highs"] = highs
                    params["lows"] = lows
                if registry_name == "VOL":
                    params["volumes"] = volumes

                result = indicator.calculate(closes, **params)

                # Get the last non-None value for the indicator
                for key, values in result.values.items():
                    target_key = ind_name if ind_name != registry_name else key
                    for v in reversed(values):
                        if v is not None:
                            indicator_values[target_key] = float(v)
                            break

            if conditions.evaluate(indicator_values):
                results.append(ScreenResult(symbol=symbol, indicator_values=indicator_values))

        if sort_by and results:
            results.sort(
                key=lambda r: r.indicator_values.get(sort_by, 0),
                reverse=(sort_order == "desc"),
            )

        return results
```

- [ ] **Step 2.3: Run tests — verify PASS**
- [ ] **Step 2.4: Commit**: `feat: add ScreenerEngine with condition evaluation and sorting`

---

## Task 3: Industry Low-PE Screener

**Files:**
- Create: `backend/app/modules/screener/industry.py`
- Create: `backend/tests/unit/modules/test_industry_screener.py`

- [ ] **Step 1: Write test_industry_screener.py**

```python
# tests/unit/modules/test_industry_screener.py
from decimal import Decimal

from app.modules.valuation.base import ValuationData
from app.modules.screener.industry import IndustryScreener, IndustryScreenResult
from datetime import date


def _make_valuations() -> list[ValuationData]:
    return [
        ValuationData(symbol="2330.TW", name="台積電", date=date(2026, 4, 22),
                      pe_ratio=Decimal("22.5"), pb_ratio=Decimal("5.6"),
                      dividend_yield=Decimal("1.8"), industry="半導體業"),
        ValuationData(symbol="2303.TW", name="聯電", date=date(2026, 4, 22),
                      pe_ratio=Decimal("10.5"), pb_ratio=Decimal("1.2"),
                      dividend_yield=Decimal("5.0"), industry="半導體業"),
        ValuationData(symbol="3034.TW", name="聯詠", date=date(2026, 4, 22),
                      pe_ratio=Decimal("11.2"), pb_ratio=Decimal("2.8"),
                      dividend_yield=Decimal("4.5"), industry="半導體業"),
        ValuationData(symbol="2317.TW", name="鴻海", date=date(2026, 4, 22),
                      pe_ratio=Decimal("12.0"), pb_ratio=Decimal("0.7"),
                      dividend_yield=Decimal("6.5"), industry="其他電子��"),
        # Negative EPS — should be excluded
        ValuationData(symbol="9999.TW", name="虧損公司", date=date(2026, 4, 22),
                      pe_ratio=None, pb_ratio=Decimal("0.5"),
                      dividend_yield=None, industry="半導體業"),
    ]


def test_industry_averages() -> None:
    screener = IndustryScreener()
    avgs = screener.compute_industry_averages(_make_valuations())

    semi = avgs["半導體業"]
    assert semi.avg_pe is not None
    # avg of 22.5, 10.5, 11.2 = 14.73...
    assert abs(float(semi.avg_pe) - 14.73) < 0.1


def test_find_undervalued() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)

    symbols = [r.symbol for r in results]
    # 聯電 (10.5) and 聯詠 (11.2) should be below avg (14.73)
    assert "2303.TW" in symbols
    assert "3034.TW" in symbols
    # 台積電 (22.5) is above average
    assert "2330.TW" not in symbols


def test_excludes_negative_eps() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations())
    symbols = [r.symbol for r in results]
    assert "9999.TW" not in symbols


def test_result_has_z_score() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)
    for r in results:
        assert r.pe_z_score is not None
        assert r.pe_z_score < 0  # below average


def test_results_sorted_by_score() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)
    if len(results) >= 2:
        assert results[0].score >= results[1].score
```

- [ ] **Step 2: Implement industry.py**

```python
# app/modules/screener/industry.py
import statistics
from dataclasses import dataclass
from decimal import Decimal

from app.modules.valuation.base import ValuationData


@dataclass
class IndustryAverage:
    industry: str
    avg_pe: Decimal | None
    avg_pb: Decimal | None
    avg_yield: Decimal | None
    std_pe: float
    count: int


@dataclass
class IndustryScreenResult:
    symbol: str
    name: str
    industry: str
    pe_ratio: Decimal
    industry_avg_pe: Decimal
    pe_z_score: float
    score: float  # composite undervaluation score (higher = more undervalued)


class IndustryScreener:
    def compute_industry_averages(self, valuations: list[ValuationData]) -> dict[str, IndustryAverage]:
        industry_data: dict[str, list[ValuationData]] = {}
        for v in valuations:
            if v.pe_ratio is not None and v.pe_ratio > 0:
                industry_data.setdefault(v.industry, []).append(v)

        averages: dict[str, IndustryAverage] = {}
        for industry, stocks in industry_data.items():
            pe_values = [float(s.pe_ratio) for s in stocks if s.pe_ratio is not None]
            pb_values = [float(s.pb_ratio) for s in stocks if s.pb_ratio is not None]
            dy_values = [float(s.dividend_yield) for s in stocks if s.dividend_yield is not None]

            avg_pe = Decimal(str(round(statistics.mean(pe_values), 4))) if pe_values else None
            avg_pb = Decimal(str(round(statistics.mean(pb_values), 4))) if pb_values else None
            avg_dy = Decimal(str(round(statistics.mean(dy_values), 4))) if dy_values else None
            std_pe = statistics.stdev(pe_values) if len(pe_values) >= 2 else 0.0

            averages[industry] = IndustryAverage(
                industry=industry, avg_pe=avg_pe, avg_pb=avg_pb,
                avg_yield=avg_dy, std_pe=std_pe, count=len(stocks),
            )

        return averages

    def find_undervalued(
        self,
        valuations: list[ValuationData],
        z_threshold: float = -1.0,
    ) -> list[IndustryScreenResult]:
        averages = self.compute_industry_averages(valuations)
        results: list[IndustryScreenResult] = []

        for v in valuations:
            if v.pe_ratio is None or v.pe_ratio <= 0:
                continue
            if v.industry not in averages:
                continue

            avg = averages[v.industry]
            if avg.avg_pe is None or avg.std_pe == 0:
                continue

            z_score = (float(v.pe_ratio) - float(avg.avg_pe)) / avg.std_pe

            if z_score <= z_threshold:
                score = abs(z_score)
                results.append(
                    IndustryScreenResult(
                        symbol=v.symbol, name=v.name, industry=v.industry,
                        pe_ratio=v.pe_ratio, industry_avg_pe=avg.avg_pe,
                        pe_z_score=round(z_score, 4), score=round(score, 4),
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results
```

- [ ] **Step 3: Run tests — verify PASS**
- [ ] **Step 4: Commit**: `feat: add IndustryScreener with PE Z-Score undervaluation analysis`

---

## Task 4: Notification Models + Telegram Channel

**Files:**
- Create: `backend/app/models/notification.py`
- Create: `backend/app/modules/notifier/__init__.py`
- Create: `backend/app/modules/notifier/base.py`
- Create: `backend/app/modules/notifier/telegram.py`
- Create: `backend/app/modules/notifier/templates.py`
- Create: `backend/tests/unit/modules/test_telegram_notifier.py`
- Create: `backend/tests/unit/modules/test_notification_templates.py`

### Step 1: Notification models

- [ ] **Step 1.1: Create models/notification.py**

```python
# app/models/notification.py
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(50))  # price_alert, indicator_alert, schedule
    symbol: Mapped[str] = mapped_column(String(20), default="")
    conditions: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(default=None)
    channel: Mapped[str] = mapped_column(String(50))  # telegram
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
```

### Step 2: Telegram notifier + templates

- [ ] **Step 2.1: Write test_telegram_notifier.py**

```python
# tests/unit/modules/test_telegram_notifier.py
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.notifier.base import NotificationChannel
from app.modules.notifier.telegram import TelegramNotifier


def test_telegram_is_notification_channel() -> None:
    notifier = TelegramNotifier(bot_token="fake", chat_id="123")
    assert isinstance(notifier, NotificationChannel)


async def test_send_message() -> None:
    with patch("app.modules.notifier.telegram.Bot") as MockBot:
        mock_bot = AsyncMock()
        MockBot.return_value = mock_bot

        notifier = TelegramNotifier(bot_token="fake", chat_id="123")
        await notifier.send("Hello World")

        mock_bot.send_message.assert_awaited_once_with(
            chat_id="123", text="Hello World", parse_mode="HTML"
        )


async def test_send_with_custom_parse_mode() -> None:
    with patch("app.modules.notifier.telegram.Bot") as MockBot:
        mock_bot = AsyncMock()
        MockBot.return_value = mock_bot

        notifier = TelegramNotifier(bot_token="fake", chat_id="123")
        await notifier.send("**bold**", parse_mode="Markdown")

        mock_bot.send_message.assert_awaited_once_with(
            chat_id="123", text="**bold**", parse_mode="Markdown"
        )
```

- [ ] **Step 2.2: Write test_notification_templates.py**

```python
# tests/unit/modules/test_notification_templates.py
from app.modules.notifier.templates import (
    format_post_market_summary,
    format_price_alert,
    format_screener_hit,
)


def test_price_alert_format() -> None:
    msg = format_price_alert(symbol="2330.TW", name="台積電", price=890.0, condition="上穿 $890")
    assert "2330.TW" in msg
    assert "台積電" in msg
    assert "890" in msg


def test_post_market_summary_format() -> None:
    holdings = [
        {"symbol": "2330.TW", "name": "台積電", "price": 890.0, "change_pct": 2.3},
        {"symbol": "2317.TW", "name": "鴻海", "price": 178.0, "change_pct": -0.5},
    ]
    hits = [
        {"strategy": "超跌反彈", "symbol": "2412.TW", "name": "中華電", "detail": "RSI: 28.5"},
    ]
    msg = format_post_market_summary(market="台股", date="2026-04-22", holdings=holdings, screener_hits=hits)
    assert "盤後總結" in msg
    assert "台積電" in msg
    assert "+2.3%" in msg
    assert "超跌反彈" in msg


def test_screener_hit_format() -> None:
    msg = format_screener_hit(strategy="低基期", symbol="3034.TW", name="聯詠",
                              detail="PE: 11.2, 產業均: 18.5")
    assert "低基期" in msg
    assert "3034.TW" in msg
```

- [ ] **Step 2.3: Implement base.py, telegram.py, templates.py**

```python
# app/modules/notifier/base.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationChannel(Protocol):
    async def send(self, message: str, **kwargs: object) -> None: ...
```

```python
# app/modules/notifier/telegram.py
from telegram import Bot

from app.modules.notifier.base import NotificationChannel  # noqa: F401 (for isinstance check)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, message: str, **kwargs: object) -> None:
        parse_mode = str(kwargs.get("parse_mode", "HTML"))
        await self._bot.send_message(
            chat_id=self._chat_id, text=message, parse_mode=parse_mode
        )
```

```python
# app/modules/notifier/templates.py
from typing import Any


def format_price_alert(symbol: str, name: str, price: float, condition: str) -> str:
    return f"<b>[到價通知]</b> {symbol} {name}\n價格: ${price}\n條件: {condition}"


def format_screener_hit(strategy: str, symbol: str, name: str, detail: str) -> str:
    return f"  {strategy}: {symbol} {name} ({detail})"


def format_post_market_summary(
    market: str,
    date: str,
    holdings: list[dict[str, Any]],
    screener_hits: list[dict[str, Any]],
) -> str:
    lines = [f"<b>[盤後總結]</b> {date} {market}", ""]

    if holdings:
        lines.append("<b>持股表現：</b>")
        for h in holdings:
            sign = "+" if h["change_pct"] >= 0 else ""
            lines.append(f"  {h['symbol']} {h['name']}  ${h['price']} ({sign}{h['change_pct']}%)")
        lines.append("")

    if screener_hits:
        lines.append("<b>今日篩選命中：</b>")
        for hit in screener_hits:
            lines.append(format_screener_hit(hit["strategy"], hit["symbol"], hit["name"], hit["detail"]))

    return "\n".join(lines)
```

- [ ] **Step 2.4: Run tests — verify PASS**
- [ ] **Step 2.5: Commit**: `feat: add Telegram notifier with message templates`

---

## Task 5: Notification Scheduler

**Files:**
- Create: `backend/app/modules/notifier/scheduler.py`
- Create: `backend/tests/unit/modules/test_notification_scheduler.py`

- [ ] **Step 1: Write test_notification_scheduler.py**

```python
# tests/unit/modules/test_notification_scheduler.py
from unittest.mock import AsyncMock, patch

from app.modules.notifier.scheduler import NotificationScheduler


async def test_schedule_post_market_tw() -> None:
    mock_channel = AsyncMock()
    scheduler = NotificationScheduler(channel=mock_channel)

    with patch.object(scheduler, "_build_post_market_message", return_value="test message"):
        await scheduler.send_post_market_summary(market="TW")
        mock_channel.send.assert_awaited_once_with("test message")


async def test_schedule_pre_market_tw() -> None:
    mock_channel = AsyncMock()
    scheduler = NotificationScheduler(channel=mock_channel)

    with patch.object(scheduler, "_build_pre_market_message", return_value="pre-market msg"):
        await scheduler.send_pre_market_summary(market="TW")
        mock_channel.send.assert_awaited_once_with("pre-market msg")


def test_dedup_same_day() -> None:
    scheduler = NotificationScheduler(channel=AsyncMock())
    key = ("price_alert", "2330.TW", "2026-04-22")
    assert scheduler.should_send(key) is True
    scheduler.mark_sent(key)
    assert scheduler.should_send(key) is False


def test_dedup_different_day() -> None:
    scheduler = NotificationScheduler(channel=AsyncMock())
    key1 = ("price_alert", "2330.TW", "2026-04-22")
    key2 = ("price_alert", "2330.TW", "2026-04-23")
    scheduler.mark_sent(key1)
    assert scheduler.should_send(key2) is True
```

- [ ] **Step 2: Implement scheduler.py**

```python
# app/modules/notifier/scheduler.py
from app.modules.notifier.base import NotificationChannel


class NotificationScheduler:
    def __init__(self, channel: NotificationChannel) -> None:
        self._channel = channel
        self._sent: set[tuple[str, ...]] = set()

    def should_send(self, key: tuple[str, ...]) -> bool:
        return key not in self._sent

    def mark_sent(self, key: tuple[str, ...]) -> None:
        self._sent.add(key)

    async def send_post_market_summary(self, market: str) -> None:
        message = self._build_post_market_message(market)
        await self._channel.send(message)

    async def send_pre_market_summary(self, market: str) -> None:
        message = self._build_pre_market_message(market)
        await self._channel.send(message)

    def _build_post_market_message(self, market: str) -> str:
        return f"[盤後總結] {market}"

    def _build_pre_market_message(self, market: str) -> str:
        return f"[盤前摘要] {market}"
```

- [ ] **Step 3: Run tests — verify PASS**
- [ ] **Step 4: Commit**: `feat: add NotificationScheduler with dedup logic`

---

## Task 6: Screener + Notification API Endpoints

**Files:**
- Create: `backend/app/schemas/screener.py`
- Create: `backend/app/schemas/notification.py`
- Create: `backend/app/api/v1/screener.py`
- Create: `backend/app/api/v1/notifications.py`
- Modify: `backend/app/api/v1/router.py` — add new routers
- Create: `backend/tests/integration/test_screener_api.py`
- Create: `backend/tests/integration/test_notifications_api.py`

- [ ] **Step 1: Create schemas**
- [ ] **Step 2: Create API routers**
- [ ] **Step 3: Update v1 router**
- [ ] **Step 4: Write integration tests**
- [ ] **Step 5: Run full test suite**
- [ ] **Step 6: Commit**: `feat: add screener and notification API endpoints`

---

## Task 7: Frontend Screener UI + Notification Settings

**Files:**
- Create: `frontend/src/app/screener/page.tsx`
- Create: `frontend/src/app/notifications/page.tsx`
- Create: `frontend/src/components/screener/condition-builder.tsx`
- Create: `frontend/src/components/screener/results-table.tsx`
- Modify: `frontend/src/app/layout.tsx` — add navigation

- [ ] **Step 1: Build screener page with condition builder**
- [ ] **Step 2: Build notification settings page**
- [ ] **Step 3: Add top navigation bar**
- [ ] **Step 4: Verify build passes**
- [ ] **Step 5: Commit**: `feat: add screener UI and notification settings page`
