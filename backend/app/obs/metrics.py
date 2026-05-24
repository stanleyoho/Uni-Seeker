"""Plan 8 T5 — Prometheus business metrics for Uni-Seeker.

All metric objects are module-level singletons so call sites can simply
import and `.inc()` / `.set()` without managing registry state.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

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
