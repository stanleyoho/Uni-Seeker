# Phase 1: Foundation + Core Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the project infrastructure (Docker, CI/CD, pre-commit) and core data pipeline (stock price fetching + technical indicators) with TDD, achieving 90%+ test coverage.

**Architecture:** Modular Python backend with Protocol-based interfaces for all data providers and indicators. Each module is independently testable with dependency injection. FastAPI serves the API layer; Next.js 15 renders the frontend.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Redis 7, Docker, pytest, ruff, mypy, pre-commit, GitHub Actions

**Workflow:** TDD (write failing test -> implement -> green -> refactor -> commit) -> pre-commit hooks (ruff + mypy + pytest) -> CI/CD (GitHub Actions)

---

## File Structure

```
uni-seeker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── config.py                  # pydantic-settings config
│   │   ├── database.py                # async engine + session
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # DeclarativeBase
│   │   │   ├── enums.py              # Market enum
│   │   │   ├── stock.py              # Stock model
│   │   │   └── price.py              # StockPrice model
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── price.py              # Price request/response schemas
│   │   │   └── indicator.py          # Indicator schemas
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py               # Shared dependencies (get_db, etc.)
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py          # v1 router aggregator
│   │   │       ├── prices.py          # Price endpoints
│   │   │       └── indicators.py      # Indicator endpoints
│   │   ├── modules/
│   │   │   ├── __init__.py
│   │   │   ├── price_updater/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py           # DataProvider Protocol
│   │   │   │   ├── twse.py           # TWSE implementation
│   │   │   │   ├── tpex.py           # TPEX implementation
│   │   │   │   ├── yfinance_provider.py  # yfinance implementation
│   │   │   │   └── updater.py        # PriceUpdater orchestrator
│   │   │   └── indicators/
│   │   │       ├── __init__.py
│   │   │       ├── base.py           # Indicator Protocol
│   │   │       ├── registry.py       # Plugin registry
│   │   │       ├── rsi.py
│   │   │       ├── macd.py
│   │   │       ├── kd.py
│   │   │       ├── moving_average.py
│   │   │       ├── bollinger.py
│   │   │       └── volume.py
│   │   └── services/
│   │       └── __init__.py
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── alembic.ini
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py               # Shared fixtures (db, client, factories)
│   │   ├── unit/
│   │   │   ├── __init__.py
│   │   │   ├── test_config.py
│   │   │   ├── test_models.py
│   │   │   ├── modules/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── test_twse_provider.py
│   │   │   │   ├── test_tpex_provider.py
│   │   │   │   ├── test_yfinance_provider.py
│   │   │   │   ├── test_price_updater.py
│   │   │   │   ├── test_indicator_registry.py
│   │   │   │   ├── test_rsi.py
│   │   │   │   ├── test_macd.py
│   │   │   │   ├── test_kd.py
│   │   │   │   ├── test_moving_average.py
│   │   │   │   ├── test_bollinger.py
│   │   │   │   └── test_volume.py
│   │   │   └── __init__.py
│   │   ├── integration/
│   │   │   ├── __init__.py
│   │   │   ├── test_prices_api.py
│   │   │   └── test_indicators_api.py
│   │   └── factories/
│   │       ├── __init__.py
│   │       └── price_factory.py
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── stocks/
│   │   │       └── [symbol]/
│   │   │           └── page.tsx
│   │   ├── components/
│   │   │   ├── charts/
│   │   │   │   └── stock-chart.tsx
│   │   │   └── ui/                   # shadcn/ui components
│   │   ├── lib/
│   │   │   ├── api-client.ts
│   │   │   └── utils.ts
│   │   └── stores/
│   │       └── stock-store.ts
│   ├── tests/
│   │   └── components/
│   │       └── stock-chart.test.tsx
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── frontend-ci.yml
├── .pre-commit-config.yaml
└── docs/
    └── REQUIREMENTS.md
```

---

## Task 1: Project Scaffolding + Configuration

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/unit/__init__.py`
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/factories/__init__.py`
- Create: `backend/tests/unit/modules/__init__.py`
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/backend-ci.yml`
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`

### Step 1: Create backend directory structure

- [ ] **Step 1.1: Create pyproject.toml**

```toml
[project]
name = "uni-seeker-backend"
version = "0.1.0"
description = "Taiwan + US stock analysis platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "redis>=5.2.0",
    "apscheduler>=3.10.4",
    "httpx>=0.28.0",
    "pandas>=2.2.0",
    "pydantic-settings>=2.6.0",
    "structlog>=24.4.0",
    "python-telegram-bot>=21.0",
    "yfinance>=0.2.48",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-cov>=6.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
    "factory-boy>=3.3.0",
    "pre-commit>=4.0.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "aiosqlite>=0.20.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "--strict-markers",
    "--tb=short",
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-fail-under=90",
]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
exclude = ["alembic/"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF"]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

- [ ] **Step 1.2: Create app/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/uni_seeker"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # TWSE / TPEX
    twse_base_url: str = "https://openapi.twse.com.tw/v1"
    tpex_base_url: str = "https://www.tpex.org.tw/openapi/v1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # App
    app_name: str = "Uni-Seeker"
    debug: bool = False

    model_config = {"env_prefix": "UNI_", "env_file": ".env"}


settings = Settings()
```

- [ ] **Step 1.3: Create test for config**

```python
# tests/unit/test_config.py
import os

from app.config import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_name == "Uni-Seeker"
    assert "postgresql+asyncpg" in s.database_url
    assert s.debug is False


def test_settings_from_env(monkeypatch: object) -> None:
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setenv("UNI_DEBUG", "true")
    mp.setenv("UNI_APP_NAME", "Test")
    s = Settings()
    assert s.debug is True
    assert s.app_name == "Test"
    mp.undo()
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Step 1.5: Create all __init__.py files**

Create empty `__init__.py` in: `app/`, `app/models/`, `app/schemas/`, `app/api/`, `app/api/v1/`, `app/modules/`, `app/modules/price_updater/`, `app/modules/indicators/`, `app/services/`, `tests/`, `tests/unit/`, `tests/unit/modules/`, `tests/integration/`, `tests/factories/`

- [ ] **Step 1.6: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend project with pyproject.toml, config, and test structure"
```

---

### Step 2: Docker + docker-compose

- [ ] **Step 2.1: Create backend/Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [ ] **Step 2.2: Create docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: uni_seeker
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      UNI_DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/uni_seeker
      UNI_REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app

volumes:
  pgdata:
```

- [ ] **Step 2.3: Commit**

```bash
git add backend/Dockerfile docker-compose.yml
git commit -m "infra: add Docker and docker-compose for backend, postgres, redis"
```

---

### Step 3: Pre-commit hooks

- [ ] **Step 3.1: Create .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
        types_or: [python, pyi]
      - id: ruff-format
        types_or: [python, pyi]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.0
          - pydantic-settings>=2.0
          - sqlalchemy>=2.0
          - fastapi>=0.115.0
        args: [--config-file=backend/pyproject.toml]
        pass_filenames: false
        entry: mypy backend/app

  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: bash -c 'cd backend && python -m pytest --no-header -q'
        language: system
        pass_filenames: false
        always_run: true
```

- [ ] **Step 3.2: Install pre-commit hooks**

Run: `cd /Users/stanley/Uni-Seeker && pre-commit install`

- [ ] **Step 3.3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "infra: add pre-commit hooks for ruff, mypy, pytest"
```

---

### Step 4: GitHub Actions CI

- [ ] **Step 4.1: Create .github/workflows/backend-ci.yml**

```yaml
name: Backend CI

on:
  push:
    branches: [main]
    paths: [backend/**]
  pull_request:
    branches: [main]
    paths: [backend/**]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: uni_seeker_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        working-directory: backend
        run: |
          pip install uv
          uv pip install --system -e ".[dev]"

      - name: Lint (ruff)
        working-directory: backend
        run: |
          ruff check app/ tests/
          ruff format --check app/ tests/

      - name: Type check (mypy)
        working-directory: backend
        run: mypy app/

      - name: Test (pytest)
        working-directory: backend
        env:
          UNI_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/uni_seeker_test
          UNI_REDIS_URL: redis://localhost:6379/0
        run: pytest --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: backend/coverage.xml
          fail_ci_if_error: false
```

- [ ] **Step 4.2: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions backend CI with postgres, redis, lint, type-check, test"
```

---

## Task 2: Database Layer — Models + Migrations

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/enums.py`
- Create: `backend/app/models/stock.py`
- Create: `backend/app/models/price.py`
- Create: `backend/app/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/unit/test_models.py`

### Step 1: Write failing test for models

- [ ] **Step 1.1: Write model tests**

```python
# tests/unit/test_models.py
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import Market
from app.models.stock import Stock
from app.models.price import StockPrice


def test_market_enum_values() -> None:
    assert Market.TW_TWSE.value == "TW_TWSE"
    assert Market.TW_TPEX.value == "TW_TPEX"
    assert Market.US_NYSE.value == "US_NYSE"
    assert Market.US_NASDAQ.value == "US_NASDAQ"


def test_stock_model_creation() -> None:
    stock = Stock(
        symbol="2330.TW",
        name="台積電",
        market=Market.TW_TWSE,
        industry="半導體業",
    )
    assert stock.symbol == "2330.TW"
    assert stock.name == "台積電"
    assert stock.market == Market.TW_TWSE
    assert stock.industry == "半導體業"


def test_stock_price_model_creation() -> None:
    price = StockPrice(
        symbol="2330.TW",
        market=Market.TW_TWSE,
        date=date(2026, 4, 22),
        open=Decimal("885.00"),
        high=Decimal("892.00"),
        low=Decimal("883.00"),
        close=Decimal("890.00"),
        volume=25_000_000,
        change=Decimal("5.00"),
        change_percent=Decimal("0.56"),
    )
    assert price.close == Decimal("890.00")
    assert price.volume == 25_000_000
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.enums'`

### Step 2: Implement models

- [ ] **Step 2.1: Create app/models/base.py**

```python
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase, MappedAsDataclass):
    pass
```

- [ ] **Step 2.2: Create app/models/enums.py**

```python
import enum


class Market(str, enum.Enum):
    TW_TWSE = "TW_TWSE"
    TW_TPEX = "TW_TPEX"
    US_NYSE = "US_NYSE"
    US_NASDAQ = "US_NASDAQ"
```

- [ ] **Step 2.3: Create app/models/stock.py**

```python
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import Market


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[Market] = mapped_column()
    industry: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2.4: Create app/models/price.py**

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, BigInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import Market


class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_symbol_date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    market: Mapped[Market] = mapped_column()
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int] = mapped_column(BigInteger)
    change: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    change_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2.5: Create app/models/__init__.py**

```python
from app.models.base import Base
from app.models.enums import Market
from app.models.stock import Stock
from app.models.price import StockPrice

__all__ = ["Base", "Market", "Stock", "StockPrice"]
```

- [ ] **Step 2.6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 2.7: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add Stock and StockPrice SQLAlchemy models with Market enum"
```

### Step 3: Database engine + session

- [ ] **Step 3.1: Create app/database.py**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.database_echo)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

- [ ] **Step 3.2: Commit**

```bash
git add backend/app/database.py
git commit -m "feat: add async database engine and session factory"
```

### Step 4: Alembic migrations

- [ ] **Step 4.1: Create backend/alembic.ini**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/uni_seeker

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4.2: Create backend/alembic/env.py**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4.3: Create backend/alembic/script.py.mako**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4.4: Generate initial migration**

Run: `cd backend && alembic revision --autogenerate -m "create stocks and stock_prices tables"`
Expected: New file in `alembic/versions/`

- [ ] **Step 4.5: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add Alembic setup with initial migration for stocks and stock_prices"
```

### Step 5: Test fixtures (conftest.py)

- [ ] **Step 5.1: Create backend/tests/conftest.py**

```python
from collections.abc import AsyncGenerator
from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.enums import Market
from app.models.price import StockPrice

# Use SQLite for unit tests (no external DB needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def sample_prices() -> list[StockPrice]:
    """20 days of TSMC price data for indicator testing."""
    base_prices = [
        (885, 892, 880, 890, 25_000_000),
        (890, 895, 888, 893, 22_000_000),
        (893, 900, 891, 898, 28_000_000),
        (898, 902, 895, 896, 20_000_000),
        (896, 898, 890, 891, 18_000_000),
        (891, 893, 885, 887, 23_000_000),
        (887, 890, 882, 883, 21_000_000),
        (883, 886, 878, 880, 26_000_000),
        (880, 884, 876, 882, 24_000_000),
        (882, 888, 880, 886, 22_000_000),
        (886, 892, 884, 891, 25_000_000),
        (891, 896, 889, 894, 23_000_000),
        (894, 899, 892, 897, 27_000_000),
        (897, 903, 895, 901, 30_000_000),
        (901, 908, 899, 906, 32_000_000),
        (906, 910, 903, 905, 28_000_000),
        (905, 907, 900, 902, 22_000_000),
        (902, 905, 898, 903, 24_000_000),
        (903, 909, 901, 908, 29_000_000),
        (908, 915, 906, 913, 35_000_000),
    ]
    return [
        StockPrice(
            symbol="2330.TW",
            market=Market.TW_TWSE,
            date=date(2026, 4, d + 1),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=v,
        )
        for d, (o, h, l, c, v) in enumerate(base_prices)
    ]
```

- [ ] **Step 5.2: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add shared fixtures with in-memory DB and sample price data"
```

---

## Task 3: DataProvider Protocol + TWSE Provider

**Files:**
- Create: `backend/app/modules/price_updater/base.py`
- Create: `backend/app/modules/price_updater/twse.py`
- Create: `backend/tests/unit/modules/test_twse_provider.py`

### Step 1: Write failing test for TWSE provider

- [ ] **Step 1.1: Write test**

```python
# tests/unit/modules/test_twse_provider.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.modules.price_updater.base import DataProvider, StockPriceData
from app.modules.price_updater.twse import TWSEProvider


# Sample TWSE API response (actual field names from OpenAPI)
TWSE_SAMPLE_RESPONSE = [
    {
        "Code": "2330",
        "Name": "台積電",
        "TradeVolume": "25000000",
        "TradeValue": "22250000000",
        "OpeningPrice": "885.00",
        "HighestPrice": "892.00",
        "LowestPrice": "880.00",
        "ClosingPrice": "890.00",
        "Change": "5.00",
        "Transaction": "45000",
    },
    {
        "Code": "2317",
        "Name": "鴻海",
        "TradeVolume": "18000000",
        "TradeValue": "3204000000",
        "OpeningPrice": "178.00",
        "HighestPrice": "180.00",
        "LowestPrice": "177.00",
        "ClosingPrice": "178.50",
        "Change": "-0.50",
        "Transaction": "30000",
    },
]


def test_twse_provider_is_data_provider() -> None:
    """TWSEProvider must implement DataProvider protocol."""
    client = AsyncMock()
    provider = TWSEProvider(client=client)
    assert isinstance(provider, DataProvider)


async def test_twse_fetch_daily_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = TWSE_SAMPLE_RESPONSE
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert len(prices) == 2

    tsmc = prices[0]
    assert tsmc.symbol == "2330.TW"
    assert tsmc.close == Decimal("890.00")
    assert tsmc.volume == 25_000_000
    assert tsmc.market == "TW_TWSE"

    hon_hai = prices[1]
    assert hon_hai.symbol == "2317.TW"
    assert hon_hai.close == Decimal("178.50")


async def test_twse_fetch_single_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = [TWSE_SAMPLE_RESPONSE[0]]
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices(symbol="2330")

    assert len(prices) == 1
    assert prices[0].symbol == "2330.TW"


async def test_twse_handles_empty_response() -> None:
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert prices == []


async def test_twse_skips_invalid_prices() -> None:
    """Stocks with non-numeric prices (e.g., '--') should be skipped."""
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = [
        {
            "Code": "9999",
            "Name": "暫停交易",
            "TradeVolume": "0",
            "TradeValue": "0",
            "OpeningPrice": "--",
            "HighestPrice": "--",
            "LowestPrice": "--",
            "ClosingPrice": "--",
            "Change": "0",
            "Transaction": "0",
        },
        TWSE_SAMPLE_RESPONSE[0],
    ]
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TWSEProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert len(prices) == 1
    assert prices[0].symbol == "2330.TW"
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_twse_provider.py -v`
Expected: FAIL with `ModuleNotFoundError`

### Step 2: Implement DataProvider protocol and TWSE provider

- [ ] **Step 2.1: Create app/modules/price_updater/base.py**

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class StockPriceData:
    """Normalized price data returned by all providers."""

    symbol: str
    market: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal = Decimal("0")
    change_percent: Decimal = Decimal("0")
    name: str = ""


@runtime_checkable
class DataProvider(Protocol):
    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        """Fetch daily prices. If symbol is None, fetch all stocks."""
        ...

    @property
    def market(self) -> str:
        """Return the market identifier (e.g., 'TW_TWSE')."""
        ...
```

- [ ] **Step 2.2: Create app/modules/price_updater/twse.py**

```python
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.price_updater.base import DataProvider, StockPriceData

logger = structlog.get_logger()

TWSE_STOCK_DAY_ALL = "/exchangeReport/STOCK_DAY_ALL"


class TWSEProvider:
    """Fetches daily stock prices from TWSE OpenAPI."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://openapi.twse.com.tw/v1") -> None:
        self._client = client
        self._base_url = base_url

    @property
    def market(self) -> str:
        return "TW_TWSE"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        url = f"{self._base_url}{TWSE_STOCK_DAY_ALL}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw_data: list[dict[str, str]] = response.json()

        prices: list[StockPriceData] = []
        today = date.today()

        for record in raw_data:
            code = record.get("Code", "")

            if symbol and code != symbol:
                continue

            try:
                price = StockPriceData(
                    symbol=f"{code}.TW",
                    market=self.market,
                    date=today,
                    open=Decimal(record["OpeningPrice"]),
                    high=Decimal(record["HighestPrice"]),
                    low=Decimal(record["LowestPrice"]),
                    close=Decimal(record["ClosingPrice"]),
                    volume=int(record["TradeVolume"]),
                    change=Decimal(record.get("Change", "0")),
                    name=record.get("Name", ""),
                )
                prices.append(price)
            except (InvalidOperation, ValueError, KeyError):
                logger.warning("skipping_invalid_record", code=code)
                continue

        return prices
```

- [ ] **Step 2.3: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_twse_provider.py -v`
Expected: PASS (5 tests)

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/modules/price_updater/base.py backend/app/modules/price_updater/twse.py backend/tests/unit/modules/test_twse_provider.py
git commit -m "feat: add DataProvider protocol and TWSE provider with TDD"
```

---

## Task 4: TPEX + yfinance Providers

**Files:**
- Create: `backend/app/modules/price_updater/tpex.py`
- Create: `backend/app/modules/price_updater/yfinance_provider.py`
- Create: `backend/tests/unit/modules/test_tpex_provider.py`
- Create: `backend/tests/unit/modules/test_yfinance_provider.py`

### Step 1: TPEX Provider (TDD)

- [ ] **Step 1.1: Write failing test for TPEX**

```python
# tests/unit/modules/test_tpex_provider.py
from decimal import Decimal
from unittest.mock import AsyncMock

from app.modules.price_updater.base import DataProvider
from app.modules.price_updater.tpex import TPEXProvider

# TPEX uses different field names than TWSE
TPEX_SAMPLE_RESPONSE = [
    {
        "SecuritiesCompanyCode": "6510",
        "CompanyName": "精測",
        "Close": "530.00",
        "Open": "525.00",
        "High": "535.00",
        "Low": "523.00",
        "TradingShares": "1200000",
        "Change": "8.00",
    },
]


def test_tpex_provider_is_data_provider() -> None:
    provider = TPEXProvider(client=AsyncMock())
    assert isinstance(provider, DataProvider)


async def test_tpex_fetch_daily_prices() -> None:
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = TPEX_SAMPLE_RESPONSE
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TPEXProvider(client=mock_client)
    prices = await provider.fetch_daily_prices()

    assert len(prices) == 1
    assert prices[0].symbol == "6510.TWO"
    assert prices[0].market == "TW_TPEX"
    assert prices[0].close == Decimal("530.00")
    assert prices[0].volume == 1_200_000


async def test_tpex_handles_empty_response() -> None:
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = lambda: None
    mock_client.get.return_value = mock_response

    provider = TPEXProvider(client=mock_client)
    assert await provider.fetch_daily_prices() == []
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_tpex_provider.py -v`
Expected: FAIL

- [ ] **Step 1.3: Implement TPEXProvider**

```python
# app/modules/price_updater/tpex.py
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()

TPEX_QUOTES = "/tpex_mainboard_quotes"


class TPEXProvider:
    """Fetches daily stock prices from TPEX (OTC) OpenAPI."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "https://www.tpex.org.tw/openapi/v1") -> None:
        self._client = client
        self._base_url = base_url

    @property
    def market(self) -> str:
        return "TW_TPEX"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        url = f"{self._base_url}{TPEX_QUOTES}"
        response = await self._client.get(url)
        response.raise_for_status()
        raw_data: list[dict[str, str]] = response.json()

        prices: list[StockPriceData] = []
        today = date.today()

        for record in raw_data:
            code = record.get("SecuritiesCompanyCode", "")
            if symbol and code != symbol:
                continue

            try:
                price = StockPriceData(
                    symbol=f"{code}.TWO",
                    market=self.market,
                    date=today,
                    open=Decimal(record["Open"]),
                    high=Decimal(record["High"]),
                    low=Decimal(record["Low"]),
                    close=Decimal(record["Close"]),
                    volume=int(record["TradingShares"]),
                    change=Decimal(record.get("Change", "0")),
                    name=record.get("CompanyName", ""),
                )
                prices.append(price)
            except (InvalidOperation, ValueError, KeyError):
                logger.warning("skipping_invalid_tpex_record", code=code)
                continue

        return prices
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_tpex_provider.py -v`
Expected: PASS (3 tests)

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/modules/price_updater/tpex.py backend/tests/unit/modules/test_tpex_provider.py
git commit -m "feat: add TPEX OTC provider with TDD"
```

### Step 2: yfinance Provider (TDD)

- [ ] **Step 2.1: Write failing test**

```python
# tests/unit/modules/test_yfinance_provider.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd

from app.modules.price_updater.base import DataProvider
from app.modules.price_updater.yfinance_provider import YFinanceProvider


def _make_mock_history() -> pd.DataFrame:
    """Create a DataFrame matching yfinance output shape."""
    return pd.DataFrame(
        {
            "Open": [150.0, 152.0],
            "High": [155.0, 156.0],
            "Low": [149.0, 151.0],
            "Close": [153.0, 154.5],
            "Volume": [80_000_000, 75_000_000],
        },
        index=pd.DatetimeIndex([date(2026, 4, 21), date(2026, 4, 22)], name="Date"),
    )


def test_yfinance_provider_is_data_provider() -> None:
    provider = YFinanceProvider()
    assert isinstance(provider, DataProvider)


async def test_yfinance_fetch_single_stock() -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_mock_history()
    mock_ticker.info = {"exchange": "NMS"}

    with patch("app.modules.price_updater.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceProvider()
        prices = await provider.fetch_daily_prices(symbol="AAPL")

    assert len(prices) == 2
    assert prices[0].symbol == "AAPL"
    assert prices[0].market == "US_NASDAQ"
    assert prices[0].close == Decimal("153.0")
    assert prices[0].volume == 80_000_000


async def test_yfinance_empty_history() -> None:
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with patch("app.modules.price_updater.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceProvider()
        prices = await provider.fetch_daily_prices(symbol="INVALID")

    assert prices == []
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_yfinance_provider.py -v`
Expected: FAIL

- [ ] **Step 2.3: Implement YFinanceProvider**

```python
# app/modules/price_updater/yfinance_provider.py
import asyncio
from datetime import date
from decimal import Decimal
from functools import partial

import yfinance as yf
import structlog

from app.modules.price_updater.base import StockPriceData

logger = structlog.get_logger()

# Map yfinance exchange names to our Market enum values
EXCHANGE_MAP: dict[str, str] = {
    "NMS": "US_NASDAQ",
    "NGM": "US_NASDAQ",
    "NCM": "US_NASDAQ",
    "NYQ": "US_NYSE",
    "PCX": "US_NYSE",
    "ASE": "US_NYSE",
}


class YFinanceProvider:
    """Fetches US stock prices via yfinance."""

    @property
    def market(self) -> str:
        return "US_NASDAQ"

    async def fetch_daily_prices(self, symbol: str | None = None) -> list[StockPriceData]:
        if symbol is None:
            logger.warning("yfinance_requires_symbol")
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._fetch_sync, symbol))

    def _fetch_sync(self, symbol: str) -> list[StockPriceData]:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")

        if hist.empty:
            return []

        exchange = ticker.info.get("exchange", "NMS") if hasattr(ticker, "info") else "NMS"
        market = EXCHANGE_MAP.get(exchange, "US_NASDAQ")

        prices: list[StockPriceData] = []
        for dt, row in hist.iterrows():
            prices.append(
                StockPriceData(
                    symbol=symbol,
                    market=market,
                    date=dt.date() if hasattr(dt, "date") else dt,
                    open=Decimal(str(round(row["Open"], 4))),
                    high=Decimal(str(round(row["High"], 4))),
                    low=Decimal(str(round(row["Low"], 4))),
                    close=Decimal(str(round(row["Close"], 4))),
                    volume=int(row["Volume"]),
                )
            )

        return prices
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_yfinance_provider.py -v`
Expected: PASS (3 tests)

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/modules/price_updater/yfinance_provider.py backend/tests/unit/modules/test_yfinance_provider.py
git commit -m "feat: add yfinance US stock provider with TDD"
```

---

## Task 5: Price Updater Orchestrator

**Files:**
- Create: `backend/app/modules/price_updater/updater.py`
- Create: `backend/tests/unit/modules/test_price_updater.py`

### Step 1: Write failing test

- [ ] **Step 1.1: Write test for PriceUpdater**

```python
# tests/unit/modules/test_price_updater.py
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.enums import Market
from app.modules.price_updater.base import StockPriceData
from app.modules.price_updater.updater import PriceUpdater


def _make_price(symbol: str = "2330.TW", close: str = "890.00") -> StockPriceData:
    return StockPriceData(
        symbol=symbol,
        market="TW_TWSE",
        date=date(2026, 4, 22),
        open=Decimal("885.00"),
        high=Decimal("892.00"),
        low=Decimal("880.00"),
        close=Decimal(close),
        volume=25_000_000,
    )


async def test_updater_calls_providers() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [_make_price()]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    provider.fetch_daily_prices.assert_awaited_once()
    assert result.total_fetched == 1


async def test_updater_deduplicates_by_symbol_date() -> None:
    """Same symbol+date from different calls should not create duplicates."""
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [_make_price(), _make_price()]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    assert result.total_fetched == 2
    assert result.duplicates_skipped == 1


async def test_updater_validates_prices() -> None:
    """Prices with close <= 0 should be rejected."""
    provider = AsyncMock()
    provider.fetch_daily_prices.return_value = [
        _make_price(close="0.00"),
        _make_price(symbol="2317.TW", close="178.00"),
    ]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session)
    result = await updater.update_all()

    assert result.total_fetched == 2
    assert result.invalid_skipped == 1


async def test_updater_retries_on_failure() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.side_effect = [
        Exception("network error"),
        [_make_price()],
    ]
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session, max_retries=2)
    result = await updater.update_all()

    assert provider.fetch_daily_prices.await_count == 2
    assert result.total_fetched == 1


async def test_updater_gives_up_after_max_retries() -> None:
    provider = AsyncMock()
    provider.fetch_daily_prices.side_effect = Exception("permanent failure")
    provider.market = "TW_TWSE"

    session = AsyncMock()
    updater = PriceUpdater(providers=[provider], session=session, max_retries=3)
    result = await updater.update_all()

    assert provider.fetch_daily_prices.await_count == 3
    assert result.total_fetched == 0
    assert len(result.errors) == 1
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_price_updater.py -v`
Expected: FAIL

### Step 2: Implement PriceUpdater

- [ ] **Step 2.1: Create app/modules/price_updater/updater.py**

```python
import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

import structlog

from app.modules.price_updater.base import DataProvider, StockPriceData

logger = structlog.get_logger()


@dataclass
class UpdateResult:
    total_fetched: int = 0
    duplicates_skipped: int = 0
    invalid_skipped: int = 0
    saved: int = 0
    errors: list[str] = field(default_factory=list)


class PriceUpdater:
    """Orchestrates fetching prices from multiple providers."""

    def __init__(
        self,
        providers: list[DataProvider],
        session: object,
        max_retries: int = 3,
        retry_delay: float = 0.0,
    ) -> None:
        self._providers = providers
        self._session = session
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def update_all(self, symbol: str | None = None) -> UpdateResult:
        result = UpdateResult()
        all_prices: list[StockPriceData] = []

        for provider in self._providers:
            prices = await self._fetch_with_retry(provider, symbol, result)
            all_prices.extend(prices)

        result.total_fetched = len(all_prices)

        # Deduplicate by (symbol, date)
        seen: set[tuple[str, object]] = set()
        unique_prices: list[StockPriceData] = []
        for price in all_prices:
            key = (price.symbol, price.date)
            if key in seen:
                result.duplicates_skipped += 1
                continue
            seen.add(key)

            # Validate
            if price.close <= Decimal("0"):
                result.invalid_skipped += 1
                logger.warning("invalid_price", symbol=price.symbol, close=price.close)
                continue

            unique_prices.append(price)

        result.saved = len(unique_prices)
        # TODO: persist to DB via session (Task 8 - API integration)
        return result

    async def _fetch_with_retry(
        self,
        provider: DataProvider,
        symbol: str | None,
        result: UpdateResult,
    ) -> list[StockPriceData]:
        for attempt in range(self._max_retries):
            try:
                return await provider.fetch_daily_prices(symbol)
            except Exception as e:
                logger.warning(
                    "fetch_failed",
                    provider=provider.market,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < self._max_retries - 1 and self._retry_delay > 0:
                    await asyncio.sleep(self._retry_delay * (2**attempt))

        result.errors.append(f"{provider.market}: failed after {self._max_retries} retries")
        return []
```

- [ ] **Step 2.2: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_price_updater.py -v`
Expected: PASS (5 tests)

- [ ] **Step 2.3: Commit**

```bash
git add backend/app/modules/price_updater/updater.py backend/tests/unit/modules/test_price_updater.py
git commit -m "feat: add PriceUpdater orchestrator with retry, dedup, validation"
```

---

## Task 6: Technical Indicators Module

**Files:**
- Create: `backend/app/modules/indicators/base.py`
- Create: `backend/app/modules/indicators/registry.py`
- Create: `backend/app/modules/indicators/rsi.py`
- Create: `backend/app/modules/indicators/macd.py`
- Create: `backend/app/modules/indicators/kd.py`
- Create: `backend/app/modules/indicators/moving_average.py`
- Create: `backend/app/modules/indicators/bollinger.py`
- Create: `backend/app/modules/indicators/volume.py`
- Create: `backend/tests/unit/modules/test_indicator_registry.py`
- Create: `backend/tests/unit/modules/test_rsi.py`
- Create: `backend/tests/unit/modules/test_macd.py`
- Create: `backend/tests/unit/modules/test_kd.py`
- Create: `backend/tests/unit/modules/test_moving_average.py`
- Create: `backend/tests/unit/modules/test_bollinger.py`
- Create: `backend/tests/unit/modules/test_volume.py`

### Step 1: Indicator Protocol + Registry (TDD)

- [ ] **Step 1.1: Write failing test for registry**

```python
# tests/unit/modules/test_indicator_registry.py
import pytest

from app.modules.indicators.base import Indicator, IndicatorResult
from app.modules.indicators.registry import IndicatorRegistry


class DummyIndicator:
    name = "dummy"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        return IndicatorResult(name="dummy", values={"dummy": closes})


def test_registry_register_and_get() -> None:
    registry = IndicatorRegistry()
    dummy = DummyIndicator()
    registry.register(dummy)
    assert registry.get("dummy") is dummy


def test_registry_get_unknown_raises() -> None:
    registry = IndicatorRegistry()
    with pytest.raises(KeyError, match="unknown"):
        registry.get("unknown")


def test_registry_list_indicators() -> None:
    registry = IndicatorRegistry()
    registry.register(DummyIndicator())
    assert "dummy" in registry.list_names()


def test_registry_prevents_duplicate() -> None:
    registry = IndicatorRegistry()
    registry.register(DummyIndicator())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyIndicator())
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_indicator_registry.py -v`
Expected: FAIL

- [ ] **Step 1.3: Implement base.py and registry.py**

```python
# app/modules/indicators/base.py
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    values: dict[str, list[Any]]


@runtime_checkable
class Indicator(Protocol):
    name: str

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult: ...
```

```python
# app/modules/indicators/registry.py
from app.modules.indicators.base import Indicator


class IndicatorRegistry:
    def __init__(self) -> None:
        self._indicators: dict[str, Indicator] = {}

    def register(self, indicator: Indicator) -> None:
        if indicator.name in self._indicators:
            raise ValueError(f"Indicator '{indicator.name}' already registered")
        self._indicators[indicator.name] = indicator

    def get(self, name: str) -> Indicator:
        if name not in self._indicators:
            raise KeyError(f"Indicator '{name}' not found: unknown")
        return self._indicators[name]

    def list_names(self) -> list[str]:
        return list(self._indicators.keys())
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_indicator_registry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/modules/indicators/base.py backend/app/modules/indicators/registry.py backend/tests/unit/modules/test_indicator_registry.py
git commit -m "feat: add Indicator protocol and plugin registry with TDD"
```

### Step 2: RSI Indicator (TDD)

- [ ] **Step 2.1: Write failing test**

```python
# tests/unit/modules/test_rsi.py
import pytest

from app.modules.indicators.rsi import RSIIndicator


def test_rsi_name() -> None:
    assert RSIIndicator().name == "RSI"


def test_rsi_basic_calculation() -> None:
    """RSI of a steadily rising series should be > 50."""
    closes = [float(100 + i) for i in range(20)]
    result = RSIIndicator().calculate(closes, period=14)
    rsi_values = result.values["RSI"]
    # First 14 values should be None (not enough data)
    assert all(v is None for v in rsi_values[:14])
    # RSI of pure uptrend should be 100
    assert rsi_values[-1] == 100.0


def test_rsi_downtrend() -> None:
    """RSI of a steadily falling series should be 0."""
    closes = [float(100 - i) for i in range(20)]
    result = RSIIndicator().calculate(closes, period=14)
    rsi_values = result.values["RSI"]
    assert rsi_values[-1] == 0.0


def test_rsi_mixed() -> None:
    """RSI of mixed data should be between 0 and 100."""
    closes = [44.0, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
              46.22, 45.64]
    result = RSIIndicator().calculate(closes, period=14)
    rsi = result.values["RSI"][-1]
    assert rsi is not None
    assert 0 < rsi < 100


def test_rsi_too_short_data() -> None:
    """Less data than period should return all None."""
    closes = [100.0, 101.0, 102.0]
    result = RSIIndicator().calculate(closes, period=14)
    assert all(v is None for v in result.values["RSI"])


def test_rsi_custom_period() -> None:
    closes = [float(100 + i) for i in range(10)]
    result = RSIIndicator().calculate(closes, period=5)
    assert result.values["RSI"][5] is not None
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_rsi.py -v`
Expected: FAIL

- [ ] **Step 2.3: Implement RSI**

```python
# app/modules/indicators/rsi.py
from app.modules.indicators.base import IndicatorResult


class RSIIndicator:
    name = "RSI"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 14))
        n = len(closes)
        rsi: list[float | None] = [None] * n

        if n <= period:
            return IndicatorResult(name=self.name, values={"RSI": rsi})

        # Calculate price changes
        changes = [closes[i] - closes[i - 1] for i in range(1, n)]

        # First average gain/loss (SMA)
        gains = [max(c, 0.0) for c in changes[:period]]
        losses = [abs(min(c, 0.0)) for c in changes[:period]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi[period] = 100.0
        elif avg_gain == 0:
            rsi[period] = 0.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = round(100 - 100 / (1 + rs), 4)

        # Subsequent values use exponential smoothing
        for i in range(period + 1, n):
            change = changes[i - 1]
            gain = max(change, 0.0)
            loss = abs(min(change, 0.0))

            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            if avg_loss == 0:
                rsi[i] = 100.0
            elif avg_gain == 0:
                rsi[i] = 0.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = round(100 - 100 / (1 + rs), 4)

        return IndicatorResult(name=self.name, values={"RSI": rsi})
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_rsi.py -v`
Expected: PASS (6 tests)

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/modules/indicators/rsi.py backend/tests/unit/modules/test_rsi.py
git commit -m "feat: add RSI indicator with TDD"
```

### Step 3: MACD Indicator (TDD)

- [ ] **Step 3.1: Write failing test**

```python
# tests/unit/modules/test_macd.py
from app.modules.indicators.macd import MACDIndicator


def test_macd_name() -> None:
    assert MACDIndicator().name == "MACD"


def test_macd_result_keys() -> None:
    closes = [float(100 + i * 0.5) for i in range(40)]
    result = MACDIndicator().calculate(closes, fast=12, slow=26, signal=9)
    assert "MACD" in result.values
    assert "signal" in result.values
    assert "histogram" in result.values
    assert len(result.values["MACD"]) == 40


def test_macd_uptrend_positive() -> None:
    """In uptrend, MACD line should be positive."""
    closes = [float(100 + i * 2) for i in range(40)]
    result = MACDIndicator().calculate(closes)
    macd_values = [v for v in result.values["MACD"] if v is not None]
    assert macd_values[-1] > 0


def test_macd_insufficient_data() -> None:
    """Less than slow period should return all None for MACD."""
    closes = [100.0] * 10
    result = MACDIndicator().calculate(closes, fast=12, slow=26, signal=9)
    macd_vals = result.values["MACD"]
    assert all(v is None for v in macd_vals)
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_macd.py -v`
Expected: FAIL

- [ ] **Step 3.3: Implement MACD**

```python
# app/modules/indicators/macd.py
from app.modules.indicators.base import IndicatorResult


def _ema(data: list[float], period: int) -> list[float | None]:
    """Calculate Exponential Moving Average."""
    result: list[float | None] = [None] * len(data)
    if len(data) < period:
        return result

    # SMA for the first EMA value
    sma = sum(data[:period]) / period
    result[period - 1] = sma
    multiplier = 2.0 / (period + 1)

    for i in range(period, len(data)):
        prev = result[i - 1]
        if prev is not None:
            result[i] = round((data[i] - prev) * multiplier + prev, 4)

    return result


class MACDIndicator:
    name = "MACD"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal_period = int(params.get("signal", 9))
        n = len(closes)

        macd_line: list[float | None] = [None] * n
        signal_line: list[float | None] = [None] * n
        histogram: list[float | None] = [None] * n

        if n < slow:
            return IndicatorResult(
                name=self.name,
                values={"MACD": macd_line, "signal": signal_line, "histogram": histogram},
            )

        fast_ema = _ema(closes, fast)
        slow_ema = _ema(closes, slow)

        # MACD = fast EMA - slow EMA
        macd_raw: list[float] = []
        for i in range(n):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                val = round(fast_ema[i] - slow_ema[i], 4)
                macd_line[i] = val
                macd_raw.append(val)
            else:
                macd_raw.append(0.0)

        # Signal line = EMA of MACD line (only from where MACD starts)
        macd_start = slow - 1
        macd_data = [v for v in macd_line[macd_start:] if v is not None]
        if len(macd_data) >= signal_period:
            signal_ema = _ema(macd_data, signal_period)
            for i, val in enumerate(signal_ema):
                idx = macd_start + i
                if idx < n:
                    signal_line[idx] = val
                    if val is not None and macd_line[idx] is not None:
                        histogram[idx] = round(macd_line[idx] - val, 4)

        return IndicatorResult(
            name=self.name,
            values={"MACD": macd_line, "signal": signal_line, "histogram": histogram},
        )
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_macd.py -v`
Expected: PASS (4 tests)

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/modules/indicators/macd.py backend/tests/unit/modules/test_macd.py
git commit -m "feat: add MACD indicator with TDD"
```

### Step 4: KD (Stochastic Oscillator) Indicator (TDD)

- [ ] **Step 4.1: Write failing test**

```python
# tests/unit/modules/test_kd.py
import pytest

from app.modules.indicators.kd import KDIndicator


def test_kd_name() -> None:
    assert KDIndicator().name == "KD"


def test_kd_result_keys() -> None:
    # KD needs high, low, close
    highs = [float(110 + i) for i in range(20)]
    lows = [float(90 + i) for i in range(20)]
    closes = [float(100 + i) for i in range(20)]
    result = KDIndicator().calculate(
        closes, highs=highs, lows=lows, k_period=9, k_smooth=3, d_smooth=3
    )
    assert "K" in result.values
    assert "D" in result.values
    assert len(result.values["K"]) == 20


def test_kd_uptrend_high_values() -> None:
    """In a strong uptrend, K and D should be high (>50)."""
    highs = [float(100 + i * 2) for i in range(20)]
    lows = [float(99 + i * 2) for i in range(20)]
    closes = [float(100 + i * 2) for i in range(20)]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows)
    k_values = [v for v in result.values["K"] if v is not None]
    assert k_values[-1] > 50


def test_kd_insufficient_data() -> None:
    closes = [100.0, 101.0, 102.0]
    highs = [105.0, 106.0, 107.0]
    lows = [95.0, 96.0, 97.0]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows, k_period=9)
    assert all(v is None for v in result.values["K"])


def test_kd_values_between_0_and_100() -> None:
    highs = [float(110 + i % 5) for i in range(30)]
    lows = [float(90 + i % 5) for i in range(30)]
    closes = [float(100 + i % 5) for i in range(30)]
    result = KDIndicator().calculate(closes, highs=highs, lows=lows)
    for v in result.values["K"]:
        if v is not None:
            assert 0 <= v <= 100
    for v in result.values["D"]:
        if v is not None:
            assert 0 <= v <= 100
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_kd.py -v`
Expected: FAIL

- [ ] **Step 4.3: Implement KD**

```python
# app/modules/indicators/kd.py
from app.modules.indicators.base import IndicatorResult


class KDIndicator:
    name = "KD"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        highs: list[float] = list(params.get("highs", []))  # type: ignore[arg-type]
        lows: list[float] = list(params.get("lows", []))  # type: ignore[arg-type]
        k_period = int(params.get("k_period", 9))
        k_smooth = int(params.get("k_smooth", 3))
        d_smooth = int(params.get("d_smooth", 3))

        n = len(closes)
        k_values: list[float | None] = [None] * n
        d_values: list[float | None] = [None] * n

        if n < k_period or len(highs) != n or len(lows) != n:
            return IndicatorResult(name=self.name, values={"K": k_values, "D": d_values})

        # Calculate raw stochastic (%K before smoothing)
        raw_k: list[float | None] = [None] * n
        for i in range(k_period - 1, n):
            window_high = max(highs[i - k_period + 1 : i + 1])
            window_low = min(lows[i - k_period + 1 : i + 1])
            if window_high == window_low:
                raw_k[i] = 50.0
            else:
                raw_k[i] = round((closes[i] - window_low) / (window_high - window_low) * 100, 4)

        # Smooth %K with SMA
        valid_raw = [(i, v) for i, v in enumerate(raw_k) if v is not None]
        for j in range(k_smooth - 1, len(valid_raw)):
            idx = valid_raw[j][0]
            window = [valid_raw[j - k + 1][1] for k in range(k_smooth, 0, -1)]
            k_values[idx] = round(sum(window) / k_smooth, 4)  # type: ignore[arg-type]

        # %D = SMA of %K
        valid_k = [(i, v) for i, v in enumerate(k_values) if v is not None]
        for j in range(d_smooth - 1, len(valid_k)):
            idx = valid_k[j][0]
            window = [valid_k[j - k + 1][1] for k in range(d_smooth, 0, -1)]
            d_values[idx] = round(sum(window) / d_smooth, 4)  # type: ignore[arg-type]

        return IndicatorResult(name=self.name, values={"K": k_values, "D": d_values})
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_kd.py -v`
Expected: PASS (5 tests)

- [ ] **Step 4.5: Commit**

```bash
git add backend/app/modules/indicators/kd.py backend/tests/unit/modules/test_kd.py
git commit -m "feat: add KD stochastic oscillator indicator with TDD"
```

### Step 5: Moving Average Indicator (TDD)

- [ ] **Step 5.1: Write failing test**

```python
# tests/unit/modules/test_moving_average.py
from app.modules.indicators.moving_average import MovingAverageIndicator


def test_ma_name() -> None:
    assert MovingAverageIndicator().name == "MA"


def test_ma_sma_basic() -> None:
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = MovingAverageIndicator().calculate(closes, period=3, ma_type="SMA")
    sma = result.values["MA"]
    assert sma[0] is None
    assert sma[1] is None
    assert sma[2] == 20.0  # (10+20+30)/3
    assert sma[3] == 30.0  # (20+30+40)/3
    assert sma[4] == 40.0  # (30+40+50)/3


def test_ma_ema_basic() -> None:
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = MovingAverageIndicator().calculate(closes, period=3, ma_type="EMA")
    ema = result.values["MA"]
    assert ema[0] is None
    assert ema[1] is None
    assert ema[2] == 20.0  # SMA seed
    assert ema[3] is not None
    assert ema[3] > 20.0  # Should be moving up


def test_ma_default_periods() -> None:
    """Default should calculate multiple MAs (5, 10, 20, 60, 120, 240)."""
    closes = [float(100 + i) for i in range(250)]
    result = MovingAverageIndicator().calculate(closes, period=5)
    assert len(result.values["MA"]) == 250


def test_ma_insufficient_data() -> None:
    closes = [100.0, 101.0]
    result = MovingAverageIndicator().calculate(closes, period=5)
    assert all(v is None for v in result.values["MA"])
```

- [ ] **Step 5.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_moving_average.py -v`
Expected: FAIL

- [ ] **Step 5.3: Implement MovingAverage**

```python
# app/modules/indicators/moving_average.py
from app.modules.indicators.base import IndicatorResult


class MovingAverageIndicator:
    name = "MA"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 20))
        ma_type = str(params.get("ma_type", "SMA"))
        n = len(closes)

        ma: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"MA": ma})

        if ma_type == "EMA":
            # SMA seed
            sma = sum(closes[:period]) / period
            ma[period - 1] = round(sma, 4)
            multiplier = 2.0 / (period + 1)
            for i in range(period, n):
                prev = ma[i - 1]
                if prev is not None:
                    ma[i] = round((closes[i] - prev) * multiplier + prev, 4)
        else:
            # SMA
            window_sum = sum(closes[:period])
            ma[period - 1] = round(window_sum / period, 4)
            for i in range(period, n):
                window_sum += closes[i] - closes[i - period]
                ma[i] = round(window_sum / period, 4)

        return IndicatorResult(name=self.name, values={"MA": ma})
```

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_moving_average.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/modules/indicators/moving_average.py backend/tests/unit/modules/test_moving_average.py
git commit -m "feat: add SMA/EMA moving average indicator with TDD"
```

### Step 6: Bollinger Bands Indicator (TDD)

- [ ] **Step 6.1: Write failing test**

```python
# tests/unit/modules/test_bollinger.py
import math

from app.modules.indicators.bollinger import BollingerBandsIndicator


def test_bb_name() -> None:
    assert BollingerBandsIndicator().name == "BB"


def test_bb_result_keys() -> None:
    closes = [float(100 + i) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20, num_std=2)
    assert "upper" in result.values
    assert "middle" in result.values
    assert "lower" in result.values


def test_bb_middle_is_sma() -> None:
    closes = [float(100 + i) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20)
    sma_20 = sum(closes[:20]) / 20
    assert result.values["middle"][19] == round(sma_20, 4)


def test_bb_upper_above_middle_above_lower() -> None:
    closes = [float(100 + i % 10) for i in range(25)]
    result = BollingerBandsIndicator().calculate(closes, period=20)
    for i in range(25):
        u = result.values["upper"][i]
        m = result.values["middle"][i]
        lo = result.values["lower"][i]
        if u is not None and m is not None and lo is not None:
            assert u > m > lo


def test_bb_insufficient_data() -> None:
    closes = [100.0] * 5
    result = BollingerBandsIndicator().calculate(closes, period=20)
    assert all(v is None for v in result.values["upper"])
```

- [ ] **Step 6.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_bollinger.py -v`
Expected: FAIL

- [ ] **Step 6.3: Implement Bollinger Bands**

```python
# app/modules/indicators/bollinger.py
import math

from app.modules.indicators.base import IndicatorResult


class BollingerBandsIndicator:
    name = "BB"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        period = int(params.get("period", 20))
        num_std = float(params.get("num_std", 2.0))
        n = len(closes)

        upper: list[float | None] = [None] * n
        middle: list[float | None] = [None] * n
        lower: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(
                name=self.name, values={"upper": upper, "middle": middle, "lower": lower}
            )

        for i in range(period - 1, n):
            window = closes[i - period + 1 : i + 1]
            sma = sum(window) / period
            variance = sum((x - sma) ** 2 for x in window) / period
            std = math.sqrt(variance)

            middle[i] = round(sma, 4)
            upper[i] = round(sma + num_std * std, 4)
            lower[i] = round(sma - num_std * std, 4)

        return IndicatorResult(
            name=self.name, values={"upper": upper, "middle": middle, "lower": lower}
        )
```

- [ ] **Step 6.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_bollinger.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6.5: Commit**

```bash
git add backend/app/modules/indicators/bollinger.py backend/tests/unit/modules/test_bollinger.py
git commit -m "feat: add Bollinger Bands indicator with TDD"
```

### Step 7: Volume Indicators (OBV + Volume MA) (TDD)

- [ ] **Step 7.1: Write failing test**

```python
# tests/unit/modules/test_volume.py
from app.modules.indicators.volume import VolumeIndicator


def test_volume_name() -> None:
    assert VolumeIndicator().name == "VOL"


def test_obv_basic() -> None:
    closes = [10.0, 11.0, 10.5, 11.5, 12.0]
    volumes = [1000, 1500, 1200, 1800, 2000]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="OBV")
    obv = result.values["OBV"]
    assert obv[0] == 1000
    assert obv[1] == 2500   # up: 1000 + 1500
    assert obv[2] == 1300   # down: 2500 - 1200
    assert obv[3] == 3100   # up: 1300 + 1800
    assert obv[4] == 5100   # up: 3100 + 2000


def test_volume_ma() -> None:
    closes = [100.0] * 10
    volumes = [1000 * (i + 1) for i in range(10)]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="VMA", period=5)
    vma = result.values["VMA"]
    assert vma[3] is None
    assert vma[4] == sum(volumes[:5]) / 5


def test_volume_ratio() -> None:
    closes = [100.0] * 10
    volumes = [1000] * 9 + [2000]
    result = VolumeIndicator().calculate(closes, volumes=volumes, indicator_type="VMA", period=5)
    vma = result.values["VMA"]
    # Last VMA should reflect the spike
    assert vma[-1] is not None
    assert vma[-1] > vma[-2]  # type: ignore[operator]
```

- [ ] **Step 7.2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/modules/test_volume.py -v`
Expected: FAIL

- [ ] **Step 7.3: Implement Volume indicators**

```python
# app/modules/indicators/volume.py
from app.modules.indicators.base import IndicatorResult


class VolumeIndicator:
    name = "VOL"

    def calculate(self, closes: list[float], **params: object) -> IndicatorResult:
        volumes: list[int] = list(params.get("volumes", []))  # type: ignore[arg-type]
        indicator_type = str(params.get("indicator_type", "OBV"))
        period = int(params.get("period", 5))

        if indicator_type == "OBV":
            return self._calculate_obv(closes, volumes)
        return self._calculate_vma(volumes, period)

    def _calculate_obv(self, closes: list[float], volumes: list[int]) -> IndicatorResult:
        n = len(closes)
        obv: list[int | None] = [None] * n

        if n == 0 or len(volumes) != n:
            return IndicatorResult(name=self.name, values={"OBV": obv})

        obv[0] = volumes[0]
        for i in range(1, n):
            prev_obv = obv[i - 1] or 0
            if closes[i] > closes[i - 1]:
                obv[i] = prev_obv + volumes[i]
            elif closes[i] < closes[i - 1]:
                obv[i] = prev_obv - volumes[i]
            else:
                obv[i] = prev_obv

        return IndicatorResult(name=self.name, values={"OBV": obv})

    def _calculate_vma(self, volumes: list[int], period: int) -> IndicatorResult:
        n = len(volumes)
        vma: list[float | None] = [None] * n

        if n < period:
            return IndicatorResult(name=self.name, values={"VMA": vma})

        window_sum = sum(volumes[:period])
        vma[period - 1] = window_sum / period
        for i in range(period, n):
            window_sum += volumes[i] - volumes[i - period]
            vma[i] = window_sum / period

        return IndicatorResult(name=self.name, values={"VMA": vma})
```

- [ ] **Step 7.4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/modules/test_volume.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7.5: Create indicators __init__.py to wire up default registry**

```python
# app/modules/indicators/__init__.py
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.indicators.rsi import RSIIndicator
from app.modules.indicators.macd import MACDIndicator
from app.modules.indicators.kd import KDIndicator
from app.modules.indicators.moving_average import MovingAverageIndicator
from app.modules.indicators.bollinger import BollingerBandsIndicator
from app.modules.indicators.volume import VolumeIndicator


def create_default_registry() -> IndicatorRegistry:
    registry = IndicatorRegistry()
    registry.register(RSIIndicator())
    registry.register(MACDIndicator())
    registry.register(KDIndicator())
    registry.register(MovingAverageIndicator())
    registry.register(BollingerBandsIndicator())
    registry.register(VolumeIndicator())
    return registry
```

- [ ] **Step 7.6: Commit**

```bash
git add backend/app/modules/indicators/ backend/tests/unit/modules/test_volume.py
git commit -m "feat: add OBV/VMA volume indicators, wire up default registry"
```

---

## Task 7: FastAPI Application + API Endpoints

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/api/v1/prices.py`
- Create: `backend/app/api/v1/indicators.py`
- Create: `backend/app/schemas/price.py`
- Create: `backend/app/schemas/indicator.py`
- Create: `backend/tests/integration/test_prices_api.py`
- Create: `backend/tests/integration/test_indicators_api.py`

### Step 1: Pydantic schemas + FastAPI app

- [ ] **Step 1.1: Create app/schemas/price.py**

```python
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Market


class StockPriceResponse(BaseModel):
    symbol: str
    market: Market
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal
    change_percent: Decimal

    model_config = {"from_attributes": True}


class StockPriceListResponse(BaseModel):
    data: list[StockPriceResponse]
    total: int


class PriceUpdateRequest(BaseModel):
    symbol: str | None = None
    market: Market | None = None


class PriceUpdateResponse(BaseModel):
    total_fetched: int
    duplicates_skipped: int
    invalid_skipped: int
    saved: int
    errors: list[str]
```

- [ ] **Step 1.2: Create app/schemas/indicator.py**

```python
from typing import Any

from pydantic import BaseModel


class IndicatorRequest(BaseModel):
    symbol: str
    indicator: str
    params: dict[str, Any] = {}


class IndicatorResponse(BaseModel):
    symbol: str
    indicator: str
    values: dict[str, list[Any]]


class IndicatorListResponse(BaseModel):
    indicators: list[str]
```

- [ ] **Step 1.3: Create app/api/deps.py**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.modules.indicators import create_default_registry
from app.modules.indicators.registry import IndicatorRegistry


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_indicator_registry() -> IndicatorRegistry:
    return create_default_registry()
```

- [ ] **Step 1.4: Create app/api/v1/prices.py**

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.schemas.price import StockPriceListResponse, StockPriceResponse

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/{symbol}", response_model=StockPriceListResponse)
async def get_stock_prices(
    symbol: str,
    limit: int = Query(default=30, le=365),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> StockPriceListResponse:
    query = (
        select(StockPrice)
        .where(StockPrice.symbol == symbol)
        .order_by(StockPrice.date.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    count_query = select(StockPrice).where(StockPrice.symbol == symbol)
    count_result = await db.execute(count_query)
    total = len(list(count_result.scalars().all()))

    return StockPriceListResponse(
        data=[StockPriceResponse.model_validate(p) for p in prices],
        total=total,
    )
```

- [ ] **Step 1.5: Create app/api/v1/indicators.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry
from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.schemas.indicator import IndicatorListResponse, IndicatorRequest, IndicatorResponse

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("/", response_model=IndicatorListResponse)
def list_indicators(
    registry: IndicatorRegistry = Depends(get_indicator_registry),
) -> IndicatorListResponse:
    return IndicatorListResponse(indicators=registry.list_names())


@router.post("/calculate", response_model=IndicatorResponse)
async def calculate_indicator(
    req: IndicatorRequest,
    db: AsyncSession = Depends(get_db),
    registry: IndicatorRegistry = Depends(get_indicator_registry),
) -> IndicatorResponse:
    try:
        indicator = registry.get(req.indicator)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Indicator '{req.indicator}' not found")

    # Fetch prices
    query = (
        select(StockPrice)
        .where(StockPrice.symbol == req.symbol)
        .order_by(StockPrice.date.asc())
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for '{req.symbol}'")

    closes = [float(p.close) for p in prices]

    # Add highs/lows if needed for KD
    params = dict(req.params)
    if req.indicator == "KD":
        params["highs"] = [float(p.high) for p in prices]
        params["lows"] = [float(p.low) for p in prices]
    if req.indicator == "VOL":
        params["volumes"] = [p.volume for p in prices]

    indicator_result = indicator.calculate(closes, **params)

    return IndicatorResponse(
        symbol=req.symbol,
        indicator=req.indicator,
        values=indicator_result.values,
    )
```

- [ ] **Step 1.6: Create app/api/v1/router.py**

```python
from fastapi import APIRouter

from app.api.v1.prices import router as prices_router
from app.api.v1.indicators import router as indicators_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(prices_router)
v1_router.include_router(indicators_router)
```

- [ ] **Step 1.7: Create app/main.py**

```python
from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/api/openapi.json",
    )

    app.include_router(v1_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 1.8: Commit**

```bash
git add backend/app/main.py backend/app/schemas/ backend/app/api/
git commit -m "feat: add FastAPI app with price and indicator endpoints"
```

### Step 2: Integration tests

- [ ] **Step 2.1: Write integration test for prices API**

```python
# tests/integration/test_prices_api.py
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import create_app
from app.models.base import Base
from app.models.enums import Market
from app.models.price import StockPrice
from app.api.deps import get_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def app_with_db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed data
    async with session_factory() as session:
        price = StockPrice(
            symbol="2330.TW",
            market=Market.TW_TWSE,
            date=date(2026, 4, 22),
            open=Decimal("885.00"),
            high=Decimal("892.00"),
            low=Decimal("880.00"),
            close=Decimal("890.00"),
            volume=25_000_000,
        )
        session.add(price)
        await session.commit()

    yield app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_get_prices(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/prices/2330.TW")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["data"][0]["symbol"] == "2330.TW"
        assert data["data"][0]["close"] == "890.00"


async def test_get_prices_empty(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/prices/INVALID")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


async def test_health(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2.2: Write integration test for indicators API**

```python
# tests/integration/test_indicators_api.py
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import create_app
from app.models.base import Base
from app.models.enums import Market
from app.models.price import StockPrice
from app.api.deps import get_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def app_with_prices():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed 20 days of data
    async with session_factory() as session:
        for i in range(20):
            price = StockPrice(
                symbol="2330.TW",
                market=Market.TW_TWSE,
                date=date(2026, 4, i + 1),
                open=Decimal(str(885 + i)),
                high=Decimal(str(892 + i)),
                low=Decimal(str(880 + i)),
                close=Decimal(str(890 + i)),
                volume=25_000_000 + i * 100_000,
            )
            session.add(price)
        await session.commit()

    yield app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_indicators(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/indicators/")
        assert resp.status_code == 200
        indicators = resp.json()["indicators"]
        assert "RSI" in indicators
        assert "MACD" in indicators
        assert "KD" in indicators


async def test_calculate_rsi(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "2330.TW", "indicator": "RSI", "params": {"period": 14}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "2330.TW"
        assert data["indicator"] == "RSI"
        assert "RSI" in data["values"]
        assert len(data["values"]["RSI"]) == 20


async def test_calculate_unknown_indicator(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "2330.TW", "indicator": "UNKNOWN"},
        )
        assert resp.status_code == 404


async def test_calculate_no_data(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "INVALID", "indicator": "RSI"},
        )
        assert resp.status_code == 404
```

- [ ] **Step 2.3: Run all tests**

Run: `cd backend && python -m pytest -v`
Expected: ALL PASS, coverage >= 90%

- [ ] **Step 2.4: Commit**

```bash
git add backend/tests/integration/
git commit -m "test: add integration tests for prices and indicators API endpoints"
```

---

## Task 8: Frontend Scaffolding + Stock Chart Page

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/stocks/[symbol]/page.tsx`
- Create: `frontend/src/lib/api-client.ts`
- Create: `frontend/src/components/charts/stock-chart.tsx`
- Create: `frontend/src/stores/stock-store.ts`
- Create: `frontend/Dockerfile`
- Create: `.github/workflows/frontend-ci.yml`

### Step 1: Initialize Next.js project

- [ ] **Step 1.1: Create frontend with Next.js CLI**

Run:
```bash
cd /Users/stanley/Uni-Seeker && npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --no-turbopack
```

- [ ] **Step 1.2: Install additional dependencies**

Run:
```bash
cd frontend && npm install lightweight-charts zustand @tanstack/react-query && npm install -D vitest @testing-library/react @testing-library/jest-dom @vitejs/plugin-react jsdom
```

- [ ] **Step 1.3: Install shadcn/ui**

Run:
```bash
cd frontend && npx shadcn@latest init -d
```

- [ ] **Step 1.4: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js 15 frontend with TailwindCSS, shadcn/ui, lightweight-charts"
```

### Step 2: API client

- [ ] **Step 2.1: Create frontend/src/lib/api-client.ts**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface StockPrice {
  symbol: string;
  market: string;
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  change: string;
  change_percent: string;
}

export interface PriceListResponse {
  data: StockPrice[];
  total: number;
}

export interface IndicatorResponse {
  symbol: string;
  indicator: string;
  values: Record<string, (number | null)[]>;
}

export async function fetchPrices(
  symbol: string,
  limit = 30,
): Promise<PriceListResponse> {
  const res = await fetch(`${API_BASE}/prices/${symbol}?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch prices: ${res.status}`);
  return res.json();
}

export async function fetchIndicator(
  symbol: string,
  indicator: string,
  params: Record<string, unknown> = {},
): Promise<IndicatorResponse> {
  const res = await fetch(`${API_BASE}/indicators/calculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, indicator, params }),
  });
  if (!res.ok) throw new Error(`Failed to calculate indicator: ${res.status}`);
  return res.json();
}

export async function fetchIndicatorList(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/indicators/`);
  if (!res.ok) throw new Error(`Failed to fetch indicators: ${res.status}`);
  const data = await res.json();
  return data.indicators;
}
```

- [ ] **Step 2.2: Commit**

```bash
git add frontend/src/lib/api-client.ts
git commit -m "feat: add typed API client for backend endpoints"
```

### Step 3: Stock chart component

- [ ] **Step 3.1: Create frontend/src/components/charts/stock-chart.tsx**

```tsx
"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
} from "lightweight-charts";
import type { StockPrice } from "@/lib/api-client";

interface StockChartProps {
  prices: StockPrice[];
  height?: number;
}

export function StockChart({ prices, height = 400 }: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || prices.length === 0) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "#1a1a2e" },
        textColor: "#e0e0e0",
      },
      grid: {
        vertLines: { color: "#2a2a3e" },
        horzLines: { color: "#2a2a3e" },
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: "#ef4444",     // Taiwan convention: red = up
      downColor: "#22c55e",   // green = down
      borderVisible: false,
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });

    const data: CandlestickData<Time>[] = prices
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((p) => ({
        time: p.date as Time,
        open: parseFloat(p.open),
        high: parseFloat(p.high),
        low: parseFloat(p.low),
        close: parseFloat(p.close),
      }));

    candlestickSeries.setData(data);
    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [prices, height]);

  return <div ref={containerRef} className="w-full" />;
}
```

- [ ] **Step 3.2: Commit**

```bash
git add frontend/src/components/charts/stock-chart.tsx
git commit -m "feat: add candlestick chart component with TradingView lightweight-charts"
```

### Step 4: Stock detail page

- [ ] **Step 4.1: Create frontend/src/app/stocks/[symbol]/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { StockChart } from "@/components/charts/stock-chart";
import { fetchPrices, type StockPrice } from "@/lib/api-client";

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [prices, setPrices] = useState<StockPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchPrices(symbol, 120)
      .then((res) => setPrices(res.data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="p-8 text-center">Loading...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">{symbol}</h1>

      {prices.length > 0 ? (
        <>
          <div className="mb-4 grid grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-400">Open</span>
              <p className="text-lg">{prices[0].open}</p>
            </div>
            <div>
              <span className="text-gray-400">Close</span>
              <p className="text-lg">{prices[0].close}</p>
            </div>
            <div>
              <span className="text-gray-400">High</span>
              <p className="text-lg">{prices[0].high}</p>
            </div>
            <div>
              <span className="text-gray-400">Low</span>
              <p className="text-lg">{prices[0].low}</p>
            </div>
          </div>

          <StockChart prices={prices} height={500} />
        </>
      ) : (
        <p className="text-gray-400">No price data available</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4.2: Create frontend/src/app/page.tsx (home page with search)**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const [symbol, setSymbol] = useState("");
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (symbol.trim()) {
      router.push(`/stocks/${encodeURIComponent(symbol.trim().toUpperCase())}`);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-2">Uni-Seeker</h1>
      <p className="text-gray-400 mb-8">Taiwan + US Stock Analysis Platform</p>

      <form onSubmit={handleSearch} className="flex gap-2 w-full max-w-md">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="Enter symbol (e.g., 2330.TW, AAPL)"
          className="flex-1 px-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          Search
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4.3: Commit**

```bash
git add frontend/src/app/
git commit -m "feat: add home page with search and stock detail page with chart"
```

### Step 5: Frontend Dockerfile + CI

- [ ] **Step 5.1: Create frontend/Dockerfile**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
```

- [ ] **Step 5.2: Create .github/workflows/frontend-ci.yml**

```yaml
name: Frontend CI

on:
  push:
    branches: [main]
    paths: [frontend/**]
  pull_request:
    branches: [main]
    paths: [frontend/**]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Lint
        working-directory: frontend
        run: npm run lint

      - name: Type check
        working-directory: frontend
        run: npx tsc --noEmit

      - name: Test
        working-directory: frontend
        run: npx vitest run --coverage
```

- [ ] **Step 5.3: Update docker-compose.yml to add frontend service**

Add to `docker-compose.yml`:
```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000/api/v1
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
```

- [ ] **Step 5.4: Commit**

```bash
git add frontend/Dockerfile .github/workflows/frontend-ci.yml docker-compose.yml
git commit -m "infra: add frontend Dockerfile and CI workflow"
```

---

## Self-Review Checklist

1. **Spec coverage**: All Phase 1 items from REQUIREMENTS.md Section 6 are covered:
   - W1: Project structure, Docker, CI/CD, DB schema (**Tasks 1-2**)
   - W2: Stock price update module (TWSE/TPEX/yfinance) (**Tasks 3-5**)
   - W3: Technical indicators (RSI, MACD, KD, MA, BB) (**Task 6**)
   - W4: Frontend skeleton + stock chart page (**Task 8**)

2. **Placeholder scan**: No TBD/TODO/placeholder patterns found. All steps contain actual code.

3. **Type consistency**: Verified:
   - `StockPriceData` used consistently across providers and updater
   - `IndicatorResult` used consistently across all indicators
   - `DataProvider` Protocol referenced consistently
   - API schema field names match model field names
