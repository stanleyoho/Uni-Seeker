"""Plan 8 T11 — Sentry DSN policy check.

Exit code policy:
  - ENV == "prod" and SENTRY_DSN is empty → exit 1 (CI fails)
  - otherwise                              → exit 0

Intended for CI workflows guarding production deploy boxes; local
pre-commit hooks should NOT run this (no DSN in dev is expected).
"""

import os
import sys


def main() -> int:
    env = os.getenv("ENV", "dev")
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if env != "prod":
        print(f"check_sentry_dsn: ENV={env}, skipping (only enforced in prod)")
        return 0
    if not dsn:
        print("check_sentry_dsn: ENV=prod but SENTRY_DSN is empty — FAIL", file=sys.stderr)
        return 1
    print("check_sentry_dsn: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
