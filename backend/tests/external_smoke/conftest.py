"""External API smoke tests — conftest.

These tests hit REAL upstream services (FinMind public datasets, yfinance,
Stripe signature math). They are intentionally excluded from the regular
pytest collection (see pyproject.toml `addopts --ignore=tests/external_smoke`)
and only run from the nightly `external-api-smoke.yml` workflow.

The fixtures here just bump per-test timeout because real network calls are
slower than mocked unit tests.
"""

from __future__ import annotations

# Default HTTP timeout (seconds) for any test that wants a sane upper bound.
# Individual tests may override per call.
SMOKE_HTTP_TIMEOUT: float = 60.0
