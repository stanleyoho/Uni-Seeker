"""Portfolio Tracker Phase 1 Batch A1 — tier limits loader + guard factory.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §9.

Responsibilities:
1. Load `config/tier_limits.yaml` with strict Pydantic validation (cached).
2. Provide `get_limit(tier, key)` / `has_feature(tier, feature)` helpers.
3. Provide `tier_guard(feature=..., limit_key=...)` FastAPI dependency factory
   that returns 403 when the user's tier lacks a feature flag or exceeds a
   numeric quota.

Counter registration: `TIER_LIMIT_BLOCK_TOTAL` is registered locally with a
defensive `try/except ValueError` because `prometheus_client` raises on
duplicate metric names (which happens whenever this module is imported a
second time during pytest's module reloading). Placing the counter here
keeps the change scope tight per spec §9.5 ("counter 註冊放在 tier_limits.py
內").
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, HTTPException, status
from prometheus_client import REGISTRY, Counter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import require_auth
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User
from app.obs.logging import get_logger

logger = get_logger("billing.tier_limits")


# ── Prometheus counter (duplicate-safe register) ────────────────────────────


def _register_block_counter() -> Counter:
    """Register TIER_LIMIT_BLOCK_TOTAL idempotently.

    `prometheus_client.Counter()` raises `ValueError: Duplicated timeseries`
    on second registration (happens during pytest collection or hot reload).
    On duplicate we look up the existing collector via REGISTRY internals.
    """
    name = "uni_tier_limit_block_total"
    try:
        return Counter(
            name,
            "403 responses from tier_guard(feature=/limit_key=) factory",
            labelnames=("tier", "feature_or_limit", "action"),
        )
    except ValueError:
        # Already registered (test re-import). Reach into REGISTRY to fetch
        # the existing Counter so call sites can still `.labels(...).inc()`.
        # `_names_to_collectors` is private API but stable in prometheus_client
        # 0.20.x and the only documented mechanism for this scenario.
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is None:
            # Defensive: name suffix variants (_total) are sometimes the key.
            existing = REGISTRY._names_to_collectors.get(f"{name}_total")  # type: ignore[attr-defined]
        if existing is None:
            raise
        return existing  # type: ignore[return-value]


TIER_LIMIT_BLOCK_TOTAL: Counter = _register_block_counter()


# ── Pydantic models ─────────────────────────────────────────────────────────


class TierFeatures(BaseModel):
    """Boolean feature flags per tier.

    Strict mode rejects unknown feature keys at load time so YAML typos
    surface as validation errors instead of silent `has_feature == False`.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    realized_pnl: bool
    dividends: bool
    daily_change_breakdown: bool
    multi_account: bool
    tax_export: bool
    institutional_ownership_panel: bool
    multi_currency_summary: bool
    rebalancing: bool


class TierConfig(BaseModel):
    """Per-tier quotas + features.

    `None` on numeric quotas means unlimited (PRO convention).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    max_positions: int | None
    max_trades_per_month: int | None
    max_accounts: int | None
    max_tracked_filers: int | None
    # UNI-ALERT-001 — user-defined alert rules (Free 0 / Basic 5 / Pro 20).
    # 0 is a valid "feature off" sentinel for Free; the validator below
    # accepts it specifically so a Free user with zero allowance is
    # representable without a separate boolean flag.
    max_alert_rules: int | None = 0
    features: TierFeatures

    @field_validator(
        "max_positions",
        "max_trades_per_month",
        "max_accounts",
        "max_tracked_filers",
    )
    @classmethod
    def _positive_or_none(cls, v: int | None) -> int | None:
        # spec §9.3: "validate: 數值欄位若非 None 必 > 0"
        if v is not None and v <= 0:
            raise ValueError("quota must be > 0 or null for unlimited")
        return v

    @field_validator("max_alert_rules")
    @classmethod
    def _nonneg_or_none(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("max_alert_rules must be >= 0 or null")
        return v


class AllTierLimits(BaseModel):
    """Top-level YAML schema — every UserTier must be present."""

    model_config = ConfigDict(extra="forbid", strict=True)

    free: TierConfig
    basic: TierConfig
    pro: TierConfig

    def for_tier(self, tier: UserTier) -> TierConfig:
        return getattr(self, tier.value)


# ── Loader ──────────────────────────────────────────────────────────────────


def _default_yaml_path() -> Path:
    """Resolve the bundled YAML at `<repo-root>/config/tier_limits.yaml`.

    File layout:
        Uni-Seeker/
            backend/app/modules/billing/tier_limits.py  ← this file
            config/tier_limits.yaml                     ← target

        parents[0] = billing/
        parents[1] = modules/
        parents[2] = app/
        parents[3] = backend/
        parents[4] = Uni-Seeker/   ← repo root
    """
    return Path(__file__).resolve().parents[4] / "config" / "tier_limits.yaml"


@lru_cache(maxsize=1)
def load_tier_limits(path: str | None = None) -> AllTierLimits:
    """Load + validate tier_limits.yaml; cached so disk I/O happens once.

    Args:
        path: Optional override (absolute or relative to cwd). When None,
            resolves to `<repo-root>/config/tier_limits.yaml`.

    Returns:
        Parsed `AllTierLimits` (frozen Pydantic model).

    Raises:
        FileNotFoundError: YAML missing on disk.
        pydantic.ValidationError: schema mismatch / out-of-range value.
        yaml.YAMLError: malformed YAML syntax.
    """
    yaml_path = Path(path) if path else _default_yaml_path()
    if not yaml_path.exists():
        raise FileNotFoundError(f"tier_limits.yaml not found at {yaml_path!s}")

    raw: Any = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"tier_limits.yaml must be a mapping, got {type(raw).__name__}"
        )

    config = AllTierLimits.model_validate(raw)
    logger.info(
        "tier_limits_loaded",
        path=str(yaml_path),
        tiers=list(raw.keys()),
    )
    return config


# ── Public helpers ──────────────────────────────────────────────────────────


_NUMERIC_LIMIT_KEYS = frozenset(
    {
        "max_positions",
        "max_trades_per_month",
        "max_accounts",
        "max_tracked_filers",
        "max_alert_rules",
    }
)


def get_limit(tier: UserTier, key: str) -> int | None:
    """Return numeric limit (or None for unlimited) for a tier.

    Args:
        tier: UserTier enum.
        key: One of `max_positions`, `max_trades_per_month`, `max_accounts`.

    Raises:
        KeyError: unknown limit key.
    """
    if key not in _NUMERIC_LIMIT_KEYS:
        raise KeyError(
            f"unknown limit key {key!r}; expected one of {sorted(_NUMERIC_LIMIT_KEYS)}"
        )
    tier_cfg = load_tier_limits().for_tier(tier)
    return getattr(tier_cfg, key)  # type: ignore[no-any-return]


def has_feature(tier: UserTier, feature: str) -> bool:
    """Return whether a tier has the named feature enabled.

    Args:
        tier: UserTier enum.
        feature: Attribute name of `TierFeatures` (e.g. `realized_pnl`).

    Raises:
        KeyError: unknown feature name.
    """
    features = load_tier_limits().for_tier(tier).features
    if not hasattr(features, feature):
        raise KeyError(f"unknown feature {feature!r}")
    return bool(getattr(features, feature))


# ── FastAPI dependency factory ──────────────────────────────────────────────


def tier_guard(
    feature: str | None = None,
    limit_key: str | None = None,
    current_count_provider: Callable[..., Awaitable[int]] | None = None,
) -> Callable[..., Awaitable[User]]:
    """Build a FastAPI dependency that enforces a feature flag and/or quota.

    Two complementary checks:

    1. **Feature flag**: when `feature` is set, the dependency asserts
       `has_feature(user.tier, feature)` is True or raises 403.
    2. **Numeric quota**: when `limit_key` is set, the caller must inject a
       `current_count_provider` async callable that returns the user's
       current usage (e.g. number of accounts). The dependency compares it
       against `get_limit(user.tier, limit_key)` and raises 403 when over.

    `enable_monetization=False` (dev/test) bypasses all checks — mirrors the
    behaviour of `app.middleware.tier_guard.require_tier`.

    Args:
        feature: Optional feature flag name (see `TierFeatures`).
        limit_key: Optional numeric limit name (see `_NUMERIC_LIMIT_KEYS`).
        current_count_provider: Async callable returning current usage, used
            in conjunction with `limit_key`. Receives the resolved `User`
            as its only kwarg `user=`.

    Returns:
        FastAPI dependency callable.

    Raises:
        ValueError: when neither `feature` nor `limit_key` is provided.
        HTTPException(403): at request time when the check fails.
    """
    if feature is None and limit_key is None:
        raise ValueError("tier_guard requires at least one of feature= / limit_key=")

    if limit_key is not None and limit_key not in _NUMERIC_LIMIT_KEYS:
        raise ValueError(
            f"unknown limit_key {limit_key!r}; expected one of "
            f"{sorted(_NUMERIC_LIMIT_KEYS)}"
        )

    async def _dependency(
        user: User = Depends(require_auth),
    ) -> User:
        # Toggle-off: bypass entirely (parity with require_tier).
        if not settings.enable_monetization:
            return user

        # ---- feature flag check ----------------------------------------
        if feature is not None and not has_feature(user.tier, feature):
            TIER_LIMIT_BLOCK_TOTAL.labels(
                tier=user.tier.value,
                feature_or_limit=feature,
                action="block",
            ).inc()
            logger.warning(
                "tier_guard_feature_blocked",
                tier=user.tier.value,
                feature=feature,
                user_id=user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"feature_unavailable:{feature}",
            )

        # ---- numeric quota check ---------------------------------------
        if limit_key is not None:
            limit = get_limit(user.tier, limit_key)
            if limit is not None:
                if current_count_provider is None:
                    # Mis-configuration: a quota check without a counter is
                    # meaningless. Surface as 500 because it's a programmer
                    # error, not a user-facing 403.
                    raise RuntimeError(
                        f"tier_guard(limit_key={limit_key!r}) requires "
                        "current_count_provider"
                    )
                current = await current_count_provider(user=user)
                if current >= limit:
                    TIER_LIMIT_BLOCK_TOTAL.labels(
                        tier=user.tier.value,
                        feature_or_limit=limit_key,
                        action="block",
                    ).inc()
                    logger.warning(
                        "tier_guard_limit_blocked",
                        tier=user.tier.value,
                        limit_key=limit_key,
                        current=current,
                        limit=limit,
                        user_id=user.id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"limit_exceeded:{limit_key}",
                    )

        return user

    return _dependency


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
