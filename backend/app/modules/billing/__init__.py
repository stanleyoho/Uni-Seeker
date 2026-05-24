"""Billing module — Stripe + tier limits.

Re-exports the public surface of `tier_limits` so callers can do:

    from app.modules.billing import tier_guard, has_feature
"""

from app.modules.billing.tier_limits import (
    TIER_LIMIT_BLOCK_TOTAL,
    AllTierLimits,
    TierConfig,
    TierFeatures,
    get_limit,
    has_feature,
    load_tier_limits,
    tier_guard,
)

__all__ = [
    "TIER_LIMIT_BLOCK_TOTAL",
    "AllTierLimits",
    "TierConfig",
    "TierFeatures",
    "get_limit",
    "has_feature",
    "load_tier_limits",
    "tier_guard",
]
