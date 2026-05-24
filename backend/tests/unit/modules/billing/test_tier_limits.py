"""Unit tests for `app.modules.billing.tier_limits`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §9.

Coverage (per Phase 1 Batch A1 acceptance):
 1. YAML parsing succeeds (3 tiers present)
 2. FREE numeric quota correctness
 3. PRO numeric quota = None (unlimited)
 4. `get_limit` returns per-tier value
 5. `has_feature` false case (FREE realized_pnl)
 6. `has_feature` true case (PRO all flags)
 7. `lru_cache` returns identical object on second call
 8. `tier_guard(feature=)` passes for PRO + feature enabled
 9. `tier_guard(feature=)` raises 403 for FREE missing feature
10. `tier_guard(limit_key=)` raises 403 when count >= limit
11. Pydantic strict validation rejects malformed YAML
12. `TIER_LIMIT_BLOCK_TOTAL` counter increments on block

Pattern: mirrors `tests/unit/test_tier_guard.py` (FastAPI TestClient +
`app.dependency_overrides[require_auth]`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_auth
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User
from app.modules.billing import tier_limits as tl

# ── fixtures ────────────────────────────────────────────────────────────────


def _make_user(tier: UserTier, user_id: int = 1) -> User:
    """Construct a User dataclass-style (SQLAlchemy 2.0 Mapped Dataclass).

    Mirrors helper in tests/unit/test_tier_guard.py.
    """
    user = User(
        email=f"u{user_id}@t.com",
        hashed_password="x",
        username=f"u{user_id}",
        is_active=True,
        tier=tier,
    )
    # `id` is init=False on the ORM model (server-generated). Tests need a
    # concrete value for log/labels — set after construction.
    user.id = user_id  # type: ignore[misc]
    return user


@pytest.fixture(autouse=True)
def _enable_monetization(monkeypatch):
    """Tier checks only enforce when monetization toggle is on."""
    monkeypatch.setattr(settings, "enable_monetization", True)


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """Reset the loader cache between tests so YAML overrides take effect."""
    tl.load_tier_limits.cache_clear()
    yield
    tl.load_tier_limits.cache_clear()


@pytest.fixture
def default_limits() -> tl.AllTierLimits:
    return tl.load_tier_limits()


# ── 1. YAML parses, 3 tiers present ─────────────────────────────────────────


def test_load_tier_limits_parses_yaml(default_limits: tl.AllTierLimits):
    assert isinstance(default_limits, tl.AllTierLimits)
    assert isinstance(default_limits.free, tl.TierConfig)
    assert isinstance(default_limits.basic, tl.TierConfig)
    assert isinstance(default_limits.pro, tl.TierConfig)


# ── 2. FREE numeric quotas ──────────────────────────────────────────────────


def test_free_max_positions_is_10(default_limits: tl.AllTierLimits):
    assert default_limits.free.max_positions == 10
    assert default_limits.free.max_trades_per_month == 30
    assert default_limits.free.max_accounts == 1


# ── 3. PRO unlimited (None) ─────────────────────────────────────────────────


def test_pro_max_positions_is_none(default_limits: tl.AllTierLimits):
    assert default_limits.pro.max_positions is None
    assert default_limits.pro.max_trades_per_month is None
    assert default_limits.pro.max_accounts is None


# ── 4. get_limit per tier ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tier,key,expected",
    [
        (UserTier.FREE, "max_positions", 10),
        (UserTier.FREE, "max_accounts", 1),
        (UserTier.BASIC, "max_positions", 50),
        (UserTier.BASIC, "max_trades_per_month", 200),
        (UserTier.BASIC, "max_accounts", 3),
        (UserTier.PRO, "max_positions", None),
        (UserTier.PRO, "max_accounts", None),
    ],
)
def test_get_limit_returns_correct_value(tier: UserTier, key: str, expected: int | None):
    assert tl.get_limit(tier, key) == expected


def test_get_limit_unknown_key_raises():
    with pytest.raises(KeyError):
        tl.get_limit(UserTier.FREE, "nonexistent_key")


# ── 5. FREE missing feature ─────────────────────────────────────────────────


def test_has_feature_free_no_realized_pnl():
    assert tl.has_feature(UserTier.FREE, "realized_pnl") is False
    assert tl.has_feature(UserTier.FREE, "dividends") is False
    assert tl.has_feature(UserTier.FREE, "tax_export") is False


# ── 6. PRO all features true ────────────────────────────────────────────────


def test_has_feature_pro_all_true():
    for feat in (
        "realized_pnl",
        "dividends",
        "daily_change_breakdown",
        "multi_account",
        "tax_export",
    ):
        assert tl.has_feature(UserTier.PRO, feat) is True, f"PRO missing {feat}"


def test_has_feature_unknown_raises():
    with pytest.raises(KeyError):
        tl.has_feature(UserTier.PRO, "no_such_feature")


# ── 7. lru_cache returns identical instance ─────────────────────────────────


def test_lru_cache_returns_same_object():
    a = tl.load_tier_limits()
    b = tl.load_tier_limits()
    assert a is b, "lru_cache should reuse the same AllTierLimits instance"


# ── helper: build a FastAPI app with a guarded endpoint ─────────────────────


def _make_guarded_app(
    *,
    feature: str | None = None,
    limit_key: str | None = None,
    current_count_provider=None,
) -> FastAPI:
    app = FastAPI()
    dep = tl.tier_guard(
        feature=feature,
        limit_key=limit_key,
        current_count_provider=current_count_provider,
    )

    @app.get("/guarded")
    async def guarded(user: User = Depends(dep)):
        return {"tier": user.tier.value}

    return app


# ── 8. PRO + feature passes ─────────────────────────────────────────────────


def test_tier_guard_dependency_passes_for_pro_with_feature():
    app = _make_guarded_app(feature="realized_pnl")
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.PRO)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200
    assert r.json() == {"tier": "pro"}


# ── 9. FREE missing feature → 403 ───────────────────────────────────────────


def test_tier_guard_dependency_raises_403_for_free_missing_feature():
    app = _make_guarded_app(feature="realized_pnl")
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
    assert r.json()["detail"] == "feature_unavailable:realized_pnl"


# ── 10. limit_key over quota → 403 ──────────────────────────────────────────


def test_tier_guard_dependency_raises_403_when_limit_exceeded():
    async def at_quota(*, user: User) -> int:
        # FREE max_accounts == 1, simulate user already has 1 → next create blocked.
        return 1

    app = _make_guarded_app(limit_key="max_accounts", current_count_provider=at_quota)
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
    assert r.json()["detail"] == "limit_exceeded:max_accounts"


def test_tier_guard_dependency_under_quota_passes():
    async def under_quota(*, user: User) -> int:
        return 0

    app = _make_guarded_app(limit_key="max_accounts", current_count_provider=under_quota)
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_tier_guard_pro_unlimited_skips_count_provider():
    """PRO has limit=None → provider must not be invoked (would otherwise raise)."""

    async def explode(*, user: User) -> int:
        raise AssertionError("provider must not be called for unlimited tier")

    app = _make_guarded_app(limit_key="max_accounts", current_count_provider=explode)
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.PRO)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_tier_guard_toggle_off_bypasses(monkeypatch):
    monkeypatch.setattr(settings, "enable_monetization", False)
    app = _make_guarded_app(feature="realized_pnl")
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_tier_guard_requires_one_argument():
    with pytest.raises(ValueError):
        tl.tier_guard()


def test_tier_guard_rejects_unknown_limit_key():
    with pytest.raises(ValueError):
        tl.tier_guard(limit_key="bogus")


# ── 11. invalid YAML → ValidationError ──────────────────────────────────────


def test_yaml_invalid_raises_at_load(tmp_path: Path):
    bad = tmp_path / "tier_limits.yaml"
    # Missing `basic`/`pro`, and `max_positions` set to 0 (must be > 0).
    bad.write_text(
        yaml.safe_dump(
            {
                "free": {
                    "max_positions": 0,
                    "max_trades_per_month": 30,
                    "max_accounts": 1,
                    "features": {
                        "realized_pnl": False,
                        "dividends": False,
                        "daily_change_breakdown": False,
                        "multi_account": False,
                        "tax_export": False,
                    },
                }
            }
        )
    )
    # Bypass the lru_cache by passing an explicit path (cache is keyed on
    # the path argument).
    tl.load_tier_limits.cache_clear()
    with pytest.raises(Exception) as exc_info:
        tl.load_tier_limits(str(bad))
    # Accept ValidationError or ValueError — both are signals of strict validation.
    err_name = type(exc_info.value).__name__
    assert err_name in {"ValidationError", "ValueError"}, (
        f"expected validation failure, got {err_name}: {exc_info.value}"
    )


def test_yaml_missing_raises_file_not_found(tmp_path: Path):
    missing = tmp_path / "nope.yaml"
    tl.load_tier_limits.cache_clear()
    with pytest.raises(FileNotFoundError):
        tl.load_tier_limits(str(missing))


# ── 12. counter increments on block ─────────────────────────────────────────


def _counter_value(tier: str, key: str) -> float:
    """Read current counter value for a specific label set."""
    sample = tl.TIER_LIMIT_BLOCK_TOTAL.labels(tier=tier, feature_or_limit=key, action="block")
    # prometheus_client Counter stores cumulative count in `._value.get()`.
    return sample._value.get()  # type: ignore[attr-defined]


def test_counter_increments_on_feature_block():
    before = _counter_value("free", "realized_pnl")
    app = _make_guarded_app(feature="realized_pnl")
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
    after = _counter_value("free", "realized_pnl")
    assert after == before + 1, (
        f"TIER_LIMIT_BLOCK_TOTAL not incremented: before={before}, after={after}"
    )


def test_counter_increments_on_limit_block():
    async def at_quota(*, user: User) -> int:
        return 1

    before = _counter_value("free", "max_accounts")
    app = _make_guarded_app(limit_key="max_accounts", current_count_provider=at_quota)
    app.dependency_overrides[require_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/guarded", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
    after = _counter_value("free", "max_accounts")
    assert after == before + 1


# ── 13. 13F tracker quota + feature flag (Phase 1 Batch A3) ─────────────────


def test_free_max_tracked_filers_is_1(default_limits: tl.AllTierLimits):
    assert default_limits.free.max_tracked_filers == 1


def test_basic_max_tracked_filers_is_5(default_limits: tl.AllTierLimits):
    assert default_limits.basic.max_tracked_filers == 5


def test_pro_max_tracked_filers_is_unlimited(default_limits: tl.AllTierLimits):
    assert default_limits.pro.max_tracked_filers is None


def test_free_institutional_panel_disabled():
    assert tl.has_feature(UserTier.FREE, "institutional_ownership_panel") is False
    assert tl.has_feature(UserTier.BASIC, "institutional_ownership_panel") is False


def test_pro_institutional_panel_enabled():
    assert tl.has_feature(UserTier.PRO, "institutional_ownership_panel") is True


def test_get_limit_max_tracked_filers_for_free_user():
    assert tl.get_limit(UserTier.FREE, "max_tracked_filers") == 1
    assert tl.get_limit(UserTier.BASIC, "max_tracked_filers") == 5
    assert tl.get_limit(UserTier.PRO, "max_tracked_filers") is None


def test_has_feature_institutional_ownership_panel_pro_only():
    # PRO-only feature — Free/Basic must be False, PRO must be True.
    assert tl.has_feature(UserTier.PRO, "institutional_ownership_panel") is True
    assert tl.has_feature(UserTier.FREE, "institutional_ownership_panel") is False
    assert tl.has_feature(UserTier.BASIC, "institutional_ownership_panel") is False
