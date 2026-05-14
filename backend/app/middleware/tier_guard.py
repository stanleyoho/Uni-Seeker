from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.auth import require_auth
from app.config import settings
from app.models.enums import UserTier
from app.models.user import User

# Tier ordering: FREE < BASIC < PRO
_TIER_RANK: dict[UserTier, int] = {
    UserTier.FREE: 0,
    UserTier.BASIC: 1,
    UserTier.PRO: 2,
}


def require_tier(min_tier: UserTier):
    """
    FastAPI dependency factory.

    當 settings.enable_monetization == False 時，所有用戶視為已通過任何 tier
    檢查（架構文件約定：toggle 關閉 = 全部 PRO 行為），方便開發/測試環境不被
    付費牆阻擋。Production 必須將 UNI_ENABLE_MONETIZATION=True。

    Usage:
        @router.get("/", dependencies=[Depends(require_tier(UserTier.BASIC))])
        async def endpoint(user: User = Depends(require_tier(UserTier.BASIC))):
            ...
    """

    async def _guard(current_user: User = Depends(require_auth)) -> User:
        # Feature toggle off → 全部放行（視同 PRO）
        if not settings.enable_monetization:
            return current_user
        if _TIER_RANK[current_user.tier] < _TIER_RANK[min_tier]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_tier.value} tier or above",
            )
        return current_user

    return _guard


# Risk tolerance ordering: conservative < moderate < aggressive
_RISK_RANK: dict[str, int] = {
    "conservative": 1,
    "moderate": 2,
    "aggressive": 3,
}


def require_risk_tolerance(min_level: str):
    """FastAPI dependency factory: gate access by user.risk_tolerance.

    Args:
        min_level: One of "conservative" | "moderate" | "aggressive".

    Behavior:
        - User has not completed KYC (risk_tolerance is None) → 403 kyc_required.
        - User's risk_tolerance is below min_level → 403 risk_tolerance_insufficient.
        - Otherwise pass.

    No feature toggle: compliance gating is always enforced. Tests must
    seed user.risk_tolerance explicitly to access guarded endpoints.

    Usage:
        @router.get("/whale")
        async def whale(user: User = Depends(require_risk_tolerance("moderate"))):
            ...
    """
    if min_level not in _RISK_RANK:
        raise ValueError(f"unknown risk level: {min_level!r}")

    async def _guard(current_user: User = Depends(require_auth)) -> User:
        if current_user.risk_tolerance is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="kyc_required",
            )
        if _RISK_RANK.get(current_user.risk_tolerance, 0) < _RISK_RANK[min_level]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="risk_tolerance_insufficient",
            )
        return current_user

    return _guard
