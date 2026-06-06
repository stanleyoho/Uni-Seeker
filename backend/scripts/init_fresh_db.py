"""Bootstrap a brand-new Uni-Seeker database.

When to run this:
    - First-time prod deploy onto an empty Postgres.
    - Spinning up a brand-new dev/staging DB.
    - Any time the DB needs to be recreated from scratch.

When NOT to run this:
    - On an existing DB that just needs a new migration applied — use
      `uv run alembic upgrade head` instead.
    - On the test suite — `tests/conftest.py` handles its own schema
      setup (sqlite or pg) via `Base.metadata.create_all`.

Why this exists:
    The alembic migration chain assumes a pre-existing baseline schema
    (`stocks`, `users`, etc.) that no actual migration creates. The first
    revision `0ef449ae0f1a` only creates the `monthly_revenues` table; the
    second revision `b3a1c9d2e4f5` (3NF normalize) ALTERs `stocks` and
    friends as if they already exist. On an empty DB, running
    `alembic upgrade head` therefore fails with
    `UndefinedTableError: relation "stocks" does not exist`.

    Production / dev historically bootstrap by:
        1. Calling `Base.metadata.create_all(bind)` to materialise the
           current model layout.
        2. Calling `alembic stamp head` so future delta migrations apply
           against the right starting point.

    This script wraps that two-step pattern so it's reproducible. K3a
    (2026-06-06) made the bootstrap actually runnable end-to-end:
        - the alembic DAG previously had TWO heads (UNI_PERF_001 and
          UNI_SIGFIRE_001), so `stamp head` aborted with "Multiple head
          revisions are present"; revision `3bcd5668fe84` merges them into a
          single head.
        - the `stamp head` step now runs via the alembic CLI in a subprocess
          (env.py drives the online path with `asyncio.run`, which collided
          with this script's own running loop — see `_stamp_alembic_head`).

Usage:
    cd backend
    uv run python scripts/init_fresh_db.py

    # Or with an explicit URL override:
    UNI_DATABASE_URL=postgresql+asyncpg://user:pass@host/db \\
        uv run python scripts/init_fresh_db.py

    # Dry-run (no schema changes, just print what would happen):
    uv run python scripts/init_fresh_db.py --dry-run

Safety:
    - Refuses to run if the target DB already has user data (heuristic:
      `users` table exists with rows). Override with --force.
    - Default refuses if `alembic_version` table exists (meaning the DB
      has already been bootstrapped at some point). Override with --force.

See also:
    - `daily-task/2026-05-27-DailyTask.md` Stage 3 (E2E-2 alembic baseline
      gap discovery).
    - `tests/conftest.py` for the test-suite version of this bootstrap.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from anywhere in the repo by adjusting sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# These imports must follow sys.path manipulation above — see comment.
from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402

_PG_ENUMS: list[tuple[str, tuple[str, ...]]] = [
    ("market_enum", ("TW_TWSE", "TW_TPEX", "US_NYSE", "US_NASDAQ")),
    ("user_tier_enum", ("free", "basic", "pro")),
    ("notification_status_enum", ("pending", "success", "failed")),
]


def _create_pg_enums_sync(connection) -> None:  # type: ignore[no-untyped-def]
    """Create the PG ENUM types models declare with `create_type=False`."""
    for name, values in _PG_ENUMS:
        values_sql = ", ".join(f"'{v}'" for v in values)
        connection.execute(
            text(
                f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({values_sql}); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
        )


def _detect_existing_state_sync(connection) -> dict[str, bool]:  # type: ignore[no-untyped-def]
    """Return safety flags about whether the DB has been bootstrapped before."""
    inspector = inspect(connection)
    has_alembic = inspector.has_table("alembic_version")
    has_users = inspector.has_table("users")
    has_user_rows = False
    if has_users:
        result = connection.execute(text("SELECT EXISTS (SELECT 1 FROM users LIMIT 1)"))
        has_user_rows = bool(result.scalar())
    return {
        "has_alembic_version": has_alembic,
        "has_users_table": has_users,
        "has_user_rows": has_user_rows,
    }


def _stamp_alembic_head(database_url: str) -> None:
    """Mark the latest revision as applied so future `alembic upgrade` is clean.

    Run via the alembic CLI in a *subprocess* rather than the in-process
    ``alembic.command.stamp``. The project's ``alembic/env.py`` drives the
    online path with ``asyncio.run(run_migrations_online())``; calling it from
    inside this script's own ``asyncio.run(_bootstrap(...))`` loop raises
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``.
    A subprocess gives env.py a clean event loop of its own, which is exactly
    how a human running ``alembic stamp head`` on the CLI invokes it.

    ``UNI_DATABASE_URL`` is forwarded so the stamp targets the same DB this
    script just built (alembic.ini's default URL is the dev DB).
    """
    import os
    import subprocess

    env = {**os.environ, "UNI_DATABASE_URL": database_url}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(_BACKEND_ROOT / "alembic.ini"),
            "stamp",
            "head",
        ],
        cwd=str(_BACKEND_ROOT),
        env=env,
        check=True,
    )


async def _bootstrap(database_url: str, *, dry_run: bool, force: bool) -> None:
    is_pg = database_url.startswith(("postgresql", "postgresql+asyncpg"))
    print(f"Target: {database_url}")
    print(f"Driver: {'Postgres (asyncpg)' if is_pg else 'other'}")

    engine = create_async_engine(database_url)
    try:
        # Schema creation runs in its own committed transaction. The alembic
        # stamp must happen AFTER this block (and after the engine is disposed)
        # because it shells out to a subprocess that opens its own connection
        # and event loop — see _stamp_alembic_head.
        async with engine.begin() as conn:
            state = await conn.run_sync(_detect_existing_state_sync)
            print(f"State: {state}")

            if state["has_user_rows"] and not force:
                print(
                    "❌ Refusing to bootstrap — `users` table contains rows."
                    " Use --force if you are SURE this is what you want."
                )
                return
            if state["has_alembic_version"] and not force:
                print(
                    "❌ Refusing to bootstrap — `alembic_version` table exists,"
                    " meaning this DB has already been bootstrapped. Use --force"
                    " to override (e.g. for clean teardown + rebuild)."
                )
                return

            if dry_run:
                print("✅ Dry-run: would now create PG enums, run create_all, and stamp head.")
                return

            if is_pg:
                print("→ Creating PG ENUM types ...")
                await conn.run_sync(_create_pg_enums_sync)

            print("→ Running Base.metadata.create_all ...")
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

    if dry_run:
        return

    print("→ Stamping alembic to head ...")
    _stamp_alembic_head(database_url)

    print("✅ Bootstrap complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making schema changes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip safety checks (existing alembic_version / users rows).",
    )
    args = parser.parse_args()

    database_url = str(settings.database_url)
    asyncio.run(_bootstrap(database_url, dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
