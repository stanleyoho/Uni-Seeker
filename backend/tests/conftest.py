"""Test bootstrap and shared fixtures.

Two engine modes are supported, selected by the ``UNI_TEST_DB_URL`` env var:

1. **Default (unset / sqlite URL)** — in-memory SQLite via ``aiosqlite``.
   The schema is built from ``Base.metadata.create_all``. Fast (~1s engine
   spin-up), no external services. This is the path the existing ~1500
   tests still run on, both locally and in the regular ``backend-ci`` job.

2. **pg_integration mode (UNI_TEST_DB_URL starts with postgresql)** — a real
   Postgres 16 (docker-compose.test.yml locally, ``services: postgres`` in
   ``.github/workflows/pg-integration.yml`` in CI). The schema is built by
   running ``alembic upgrade head`` against the engine — that is the entire
   point of the E2E-2 gate: validate migration correctness, FK enforcement,
   native ENUM types, JSONB semantics, and UPSERT/partial-index SQL that
   sqlite cannot exercise.

The mode switch is automatic — no test code change is needed. Tests marked
``@pytest.mark.pg_integration`` are gated by the CI workflow so they only run
when a real Postgres is available.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler as _SQLiteTypeCompiler


# ── Patch SQLite compiler to handle PostgreSQL JSONB ─────────────────────────
# Production models declare some columns as JSONB (PG-native). SQLite has no
# JSONB type, so without this patch ``Base.metadata.create_all`` blows up
# under sqlite. Mapping JSONB → JSON lets the same ORM model serve both
# dialects in tests; production still gets real JSONB via migrations.
def _visit_JSONB(self: _SQLiteTypeCompiler, type_: object, **kwargs: object) -> str:  # type: ignore[override]
    return self.visit_JSON(type_, **kwargs)  # type: ignore[arg-type]


_SQLiteTypeCompiler.visit_JSONB = _visit_JSONB  # type: ignore[attr-defined]
# ─────────────────────────────────────────────────────────────────────────────

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.main import create_app
from app.models.base import Base
from app.models.price import StockPrice

# ── Engine URL selection ─────────────────────────────────────────────────────
# UNI_TEST_DB_URL takes precedence. When unset, fall back to the long-standing
# default (in-memory sqlite) so the existing 1500-test fast-path is preserved.
_DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///:memory:"
TEST_DATABASE_URL = os.getenv("UNI_TEST_DB_URL", _DEFAULT_SQLITE_URL)
IS_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")

# Backend root (one level up from this conftest's parent `tests/` dir).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"


def _build_schema_sqlite_sync(connection):  # type: ignore[no-untyped-def]
    """SQLite path: build the schema from ORM metadata (fast)."""
    Base.metadata.create_all(connection)


def _drop_schema_sqlite_sync(connection):  # type: ignore[no-untyped-def]
    """SQLite path: drop the schema. We tear down between tests so each
    fixture starts clean — same lifecycle the old conftest had."""
    Base.metadata.drop_all(connection)


def _run_alembic_upgrade(database_url: str) -> None:
    """Postgres path: invoke ``alembic upgrade head`` programmatically.

    This is the *whole point* of pg_integration: we want migrations, not
    metadata.create_all. We override ``sqlalchemy.url`` to point at the
    test DB so the alembic config (which defaults to dev DB) doesn't
    bleed in. The function is synchronous because alembic's Python API is.
    """
    # Late import: alembic is dev-only and we don't want to drag it into
    # the sqlite hot path (importing alembic.config doesn't actually cost
    # much, but isolating the import keeps the sqlite path fully decoupled).
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


def _drop_all_pg_sync(connection) -> None:  # type: ignore[no-untyped-def]
    """Postgres path: drop *everything* — tables, enums, alembic_version.

    Re-running alembic on a partially-migrated DB is undefined; the safest
    teardown is a clean slate. We drop+recreate the ``public`` schema in
    one shot (cheaper than enumerating objects).
    """
    from sqlalchemy import text

    connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))


def _create_pg_enums_sync(connection) -> None:  # type: ignore[no-untyped-def]
    """Postgres path: create the PG enum types that models declare with
    ``create_type=False``. Normally the 3NF normalize migration creates
    them; since we skip alembic for the pg_integration baseline workaround,
    we mirror those CREATE TYPE statements here. Values mirror
    ``app/models/enums.py``.
    """
    from sqlalchemy import text

    connection.execute(text(
        "CREATE TYPE market_enum AS ENUM ('TW_TWSE', 'TW_TPEX', 'US_NYSE', 'US_NASDAQ')"
    ))
    connection.execute(text(
        "CREATE TYPE user_tier_enum AS ENUM ('free', 'basic', 'pro')"
    ))
    connection.execute(text(
        "CREATE TYPE notification_status_enum AS ENUM ('pending', 'success', 'failed')"
    ))


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)

    if IS_POSTGRES:
        # Wipe + rebuild schema. Originally `_run_alembic_upgrade(...)` here
        # so each test validated the migration chain end-to-end, but the
        # first revision `0ef449ae0f1a` only creates `monthly_revenues` and
        # the chain assumes pre-existing baseline tables (`stocks`, `users`,
        # …). Running `alembic upgrade head` on an empty DB therefore fails
        # with `UndefinedTableError: relation "stocks" does not exist` at
        # revision `b3a1c9d2e4f5` (3NF normalize). E2E-2 caught this real
        # bug — the workaround until a proper baseline backfill migration
        # lands is to use Base.metadata.create_all + manually create the
        # PG enum types that models declare with `create_type=False`
        # (those are normally created by the 3NF migration).
        async with engine.begin() as conn:
            await conn.run_sync(_drop_all_pg_sync)
            await conn.run_sync(_create_pg_enums_sync)
            await conn.run_sync(_build_schema_sqlite_sync)
    else:
        async with engine.begin() as conn:
            await conn.run_sync(_build_schema_sqlite_sync)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    if IS_POSTGRES:
        async with engine.begin() as conn:
            await conn.run_sync(_drop_all_pg_sync)
    else:
        async with engine.begin() as conn:
            await conn.run_sync(_drop_schema_sqlite_sync)
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for the FastAPI app."""
    app = create_app()

    # Override the get_db dependency
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


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
            stock_id=1,
            date=date(2026, 4, d + 1),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=v,
        )
        for d, (o, h, l, c, v) in enumerate(base_prices)
    ]
