# tests/unit/test_tier_guard.py
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.middleware.tier_guard import require_tier
from app.models.enums import UserTier
from app.models.user import User


def _make_user(tier: UserTier) -> User:
    # NOTE: 直接用 dataclass-style init 構造（SQLAlchemy 2.0 Mapped Dataclass
    # 不支援 __new__ + direct attribute assignment，instrumented attribute 會炸）。
    # id/created_at/updated_at 因 init=False 由 ORM 管理，這裡留空即可。
    return User(
        email="t@t.com",
        hashed_password="x",
        username="t",
        is_active=True,
        tier=tier,
    )


def _make_app(min_tier: UserTier) -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(user: User = Depends(require_tier(min_tier))):
        return {"tier": user.tier}

    return app


@pytest.fixture(autouse=True)
def _enable_monetization(monkeypatch):
    """預設所有 tier_guard 測試在 monetization 啟用狀態下執行。
    需要驗證 toggle 關閉行為的測試會在 fixture 之後再 monkeypatch 覆寫。"""
    from app.config import settings

    monkeypatch.setattr(settings, "enable_monetization", True)


# NOTE: Plan 原文使用 @patch("app.middleware.tier_guard.require_auth") 同時搭配
# dependency_overrides。實測 @patch 會把 require_auth 替換成 MagicMock，導致
# FastAPI inspect dep signature 時拿到 (*args, **kwargs) 變成查詢參數驗證 422。
# 正確做法為單純使用 FastAPI 提供的 app.dependency_overrides 機制覆寫，
# 因此移除 @patch decorator 並保留 dep override。
def test_free_user_accesses_free_endpoint():
    from app.auth import require_auth as real_auth

    app = _make_app(UserTier.FREE)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_free_user_blocked_from_basic_endpoint():
    """Free user must get 403 when accessing Basic-required endpoint."""
    from app.auth import require_auth as real_auth

    app = _make_app(UserTier.BASIC)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Requires basic tier or above"


def test_basic_user_blocked_from_pro_endpoint():
    """Basic user must get 403 when accessing Pro-required endpoint."""
    from app.auth import require_auth as real_auth

    app = _make_app(UserTier.PRO)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.BASIC)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403


def test_pro_user_accesses_pro_endpoint():
    """Pro user must pass Pro-required endpoint."""
    from app.auth import require_auth as real_auth

    app = _make_app(UserTier.PRO)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.PRO)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_pro_user_accesses_basic_endpoint():
    """Pro user must pass Basic-required endpoint (tier hierarchy)."""
    from app.auth import require_auth as real_auth

    app = _make_app(UserTier.BASIC)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.PRO)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200


def test_toggle_off_bypasses_tier_check(monkeypatch):
    """ENABLE_MONETIZATION=False 時，Free 用戶必須能直接通過 PRO 端點檢查。"""
    from app.auth import require_auth as real_auth
    from app.config import settings

    monkeypatch.setattr(settings, "enable_monetization", False)
    app = _make_app(UserTier.PRO)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200, "toggle off 時必須全部放行"


def test_toggle_on_enforces_tier_check(monkeypatch):
    """ENABLE_MONETIZATION=True 時，Free 用戶存取 PRO 端點仍會被 403。"""
    from app.auth import require_auth as real_auth
    from app.config import settings

    monkeypatch.setattr(settings, "enable_monetization", True)
    app = _make_app(UserTier.PRO)
    app.dependency_overrides[real_auth] = lambda: _make_user(UserTier.FREE)
    with TestClient(app) as c:
        r = c.get("/protected", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 403
