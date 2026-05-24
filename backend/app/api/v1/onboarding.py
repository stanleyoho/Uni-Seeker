"""Onboarding endpoints — KYC questionnaire + terms acceptance.

Plan 4.5 T5. Computes risk_tolerance from 5 questionnaire answers and
persists it on the user record. Also records an audit_logs entry via
the T3 stub.
"""
from __future__ import annotations

from datetime import datetime, timezone, UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import require_auth
from app.middleware.tier_guard import require_risk_tolerance
from app.models.user import User
from app.obs.logging import get_logger
from app.schemas.onboarding import KYCRequest, KYCResponse
from app.services.audit import log_audit_event

logger = get_logger(component="onboarding")
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _classify(total: int) -> str:
    if total <= 10:
        return "conservative"
    if total <= 18:
        return "moderate"
    return "aggressive"


@router.post("/kyc", response_model=KYCResponse, status_code=200)
async def submit_kyc(
    req: KYCRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> KYCResponse:
    """Submit a 5-question KYC and lock in the user's risk_tolerance."""
    total = sum(req.answers)
    risk = _classify(total)
    now = datetime.now(UTC)

    before = {"risk_tolerance": current_user.risk_tolerance}
    current_user.risk_tolerance = risk
    current_user.kyc_completed_at = now
    current_user.terms_accepted_version = req.terms_version
    current_user.terms_accepted_at = now

    await log_audit_event(
        db,
        action="kyc_completed",
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(current_user.id),
        before_state=before,
        after_state={"risk_tolerance": risk},
        metadata={"terms_version": req.terms_version},
    )

    await db.commit()
    return KYCResponse(risk_tolerance=risk)


@router.get("/risky-demo", include_in_schema=False)
async def risky_demo(
    user: User = Depends(require_risk_tolerance("moderate")),
) -> dict:
    """Placeholder endpoint demonstrating the require_risk_tolerance guard.

    Real high-risk signal endpoints (NBA Pro, crypto whale alerts) live in
    Plan 5+ and will mount this dependency themselves; this route exists
    only so the guard can be exercised end-to-end in T6.
    """
    return {"ok": True, "user_id": user.id}
