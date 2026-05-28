"""Plan 8 T5 — Prometheus business metrics for Uni-Seeker.

All metric objects are module-level singletons so call sites can simply
import and `.inc()` / `.set()` without managing registry state.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge


def _safe_counter(
    name: str, documentation: str, labelnames: tuple[str, ...]
) -> Counter:
    """Register a Counter idempotently (duplicate-safe for pytest re-imports).

    ``prometheus_client.Counter()`` raises ``ValueError: Duplicated timeseries``
    on second registration, which happens during pytest collection when modules
    are re-imported. On duplicate we fetch the existing collector via the
    REGISTRY internals — same private-API pattern as
    ``app.modules.billing.tier_limits._register_block_counter`` (stable in
    prometheus_client 0.20.x).
    """
    try:
        return Counter(name, documentation, labelnames=labelnames)
    except ValueError:
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is None:
            existing = REGISTRY._names_to_collectors.get(f"{name}_total")
        if existing is None:
            raise
        return existing  # type: ignore[return-value]

# ── tier conversion funnel ──────────────────────────────────────────────────

TIER_UPGRADE_TOTAL = Counter(
    "uni_tier_upgrade_total",
    "User tier upgrades (Free->Basic, Free->Pro, Basic->Pro)",
    labelnames=("from_tier", "to_tier", "source"),
)

TIER_DOWNGRADE_TOTAL = Counter(
    "uni_tier_downgrade_total",
    "User tier downgrades (cancellations, expiries)",
    labelnames=("from_tier", "to_tier", "reason"),
)

SUBSCRIPTION_ACTIVE = Gauge(
    "uni_subscription_active",
    "Currently active subscriptions per tier (refreshed periodically)",
    labelnames=("tier",),
)

# ── audit / compliance ──────────────────────────────────────────────────────

AUDIT_EVENT_TOTAL = Counter(
    "uni_audit_event_total",
    "audit_logs row inserts by action and actor_type",
    labelnames=("action", "actor_type"),
)

KYC_COMPLETED_TOTAL = Counter(
    "uni_kyc_completed_total",
    "Completed KYC questionnaires by resulting risk tolerance",
    labelnames=("risk_tolerance",),
)

DEVICE_BLOCKED_TOTAL = Counter(
    "uni_device_blocked_total",
    "Devices soft-blocked by reason",
    labelnames=("reason",),
)

TIER_GUARD_BLOCK_TOTAL = Counter(
    "uni_tier_guard_block_total",
    "403 responses from require_tier guard",
    labelnames=("endpoint", "required_tier", "actual_tier"),
)

# ── stripe webhook ──────────────────────────────────────────────────────────

STRIPE_WEBHOOK_TOTAL = Counter(
    "uni_stripe_webhook_total",
    "Stripe webhook events by type and outcome",
    labelnames=("event_type", "outcome"),
)

# ── sync_manager reliability ────────────────────────────────────────────────
# Added 2026-05-28 after the 2026-04-30 silent-fail incident where
# margin / revenue / per_pbr sync tasks recorded status=partial,
# records=0, error_message=None for 27 days. PR #88 fixed the underlying
# missing partial unique index; this counter (paired with mandatory
# error_message population in the scheduler except block) ensures any
# future swallowed exception is loudly observable.

SYNC_TASK_FAILURES_TOTAL: Counter = _safe_counter(
    "uni_sync_task_failures_total",
    "Sync task exceptions caught by SyncScheduler.run_task by task and error class",
    labelnames=("task", "error_type"),
)
