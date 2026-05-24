"""Plan 8 T9 — healthcheck for the FastAPI /metrics endpoint.

Usage:
    python scripts/check_metrics_healthy.py
    METRICS_URL=http://host:8000/metrics python scripts/check_metrics_healthy.py

Exits 0 when /metrics returns 200 and emits at least one expected
``uni_*`` business metric series; exits 1 otherwise with a clear reason.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from typing import List

DEFAULT_URL = "http://localhost:8000/metrics"
TIMEOUT_SECONDS = 5.0

# Subset of metric names registered in backend/app/obs/metrics.py.
EXPECTED_METRICS: List[str] = [
    "uni_tier_upgrade_total",
    "uni_tier_downgrade_total",
    "uni_subscription_active",
    "uni_audit_event_total",
    "uni_kyc_completed_total",
    "uni_device_blocked_total",
    "uni_tier_guard_block_total",
    "uni_stripe_webhook_total",
]


def main() -> int:
    url = os.environ.get("METRICS_URL", DEFAULT_URL)

    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"✗ /metrics returned HTTP {e.code} from {url}: {e.reason}")
        return 1
    except urllib.error.URLError as e:
        print(f"✗ Could not reach {url}: {e.reason}")
        return 1
    except Exception as e:  # pragma: no cover - defensive
        print(f"✗ Unexpected error fetching {url}: {e}")
        return 1

    if status != 200:
        print(f"✗ /metrics returned HTTP {status} (expected 200) from {url}")
        return 1

    found = [m for m in EXPECTED_METRICS if m in body]
    if not found:
        print(
            f"✗ /metrics responded 200 but no expected uni_* metrics "
            f"found (checked {len(EXPECTED_METRICS)} names)."
        )
        return 1

    # Count exported metric series (non-comment, non-blank lines).
    series_count = sum(
        1 for line in body.splitlines() if line and not line.startswith("#")
    )
    sample = ", ".join(found[:3])
    print(
        f"✓ /metrics healthy: {series_count} metric series detected "
        f"(sample: {sample})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
