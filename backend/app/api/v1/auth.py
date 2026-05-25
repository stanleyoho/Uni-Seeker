from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import create_access_token, hash_password, require_auth, verify_password
from app.models.user import User
from app.models.user_device import UserDevice
from app.obs.logging import get_logger
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.audit import log_audit_event
from app.services.device import compute_fingerprint

logger = get_logger(component="auth_api")
router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# ── In-memory rate limiter (per IP) ──────────────────────────────
# Production: replace with Redis-based limiter

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX = 5  # max attempts per window


def _check_rate_limit(request: Request) -> None:
    """Raise 429 if IP exceeds rate limit for auth endpoints."""
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = _rate_limit_store[ip]
    # Clean old entries
    _rate_limit_store[ip] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        logger.warning("rate_limit_exceeded", extra={"ip": ip})
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {int(_RATE_LIMIT_WINDOW)} seconds.",
        )
    _rate_limit_store[ip].append(now)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request, db: DbSession) -> TokenResponse:
    _check_rate_limit(request)

    # Check if email exists
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check if username exists
    existing_name = await db.execute(select(User).where(User.username == req.username))
    if existing_name.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        username=req.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Plan 7 T1: audit user registration
    await log_audit_event(
        db,
        action="user_register",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        after_state={"email": user.email, "username": user.username},
        metadata={"ip": request.client.host if request.client else None},
    )
    await db.commit()

    logger.info(
        "user_registered",
        extra={"email": req.email, "ip": request.client.host if request.client else "unknown"},
    )
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    _check_rate_limit(request)
    ip = request.client.host if request.client else "unknown"

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        logger.warning("login_failed", extra={"email": req.email, "ip": ip})
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Plan 7 T1: audit successful login (device_added is a separate event)
    await log_audit_event(
        db,
        action="user_login",
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"ip": ip},
    )
    # _register_device below commits; audit row will be flushed and persisted there.

    # Plan 4.5 T7: device fingerprint registry + 3-active-device limit
    await _register_device(db, user, request)

    logger.info("login_success", extra={"email": req.email, "ip": ip})
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: Annotated[User, Depends(require_auth)]) -> UserResponse:
    return UserResponse.model_validate(user)


_DEVICE_LIMIT = 3


async def _register_device(db: AsyncSession, user: User, request: Request) -> None:
    """Record / refresh the calling device; enforce the active-device limit.

    Behavior:
      - Match (user_id, fingerprint_hash) regardless of blocked status, to
        avoid the unique-constraint collision a naive ``IS NULL`` filter causes.
      - blocked row exists  -> 403 device_blocked
      - active row exists   -> update last_seen_at, no audit (avoid log spam)
      - no row exists       -> check active count; >= 3 -> 403, else INSERT + audit
    """
    fp = compute_fingerprint(request)  # type: ignore[arg-type]

    row = await db.scalar(
        select(UserDevice).where(
            UserDevice.user_id == user.id,
            UserDevice.fingerprint_hash == fp,
        )
    )
    if row is not None:
        if row.blocked_at is not None:
            raise HTTPException(status_code=403, detail="device_blocked")
        row.last_seen_at = datetime.now(UTC)
        await db.commit()
        return

    active_count = (
        await db.scalar(
            select(func.count())
            .select_from(UserDevice)
            .where(
                UserDevice.user_id == user.id,
                UserDevice.blocked_at.is_(None),
            )
        )
        or 0
    )
    if active_count >= _DEVICE_LIMIT:
        raise HTTPException(status_code=403, detail="device_limit_exceeded")

    db.add(
        UserDevice(
            user_id=user.id,
            fingerprint_hash=fp,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    )
    await log_audit_event(
        db,
        action="device_added",
        user_id=user.id,
        resource_type="user_device",
        metadata={
            "fingerprint": fp[:16] + "...",
            "ip": request.client.host if request.client else "unknown",
        },
    )
    await db.commit()
