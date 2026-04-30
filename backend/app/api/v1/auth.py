from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import create_access_token, hash_password, require_auth, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)
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

    logger.info("user_registered", extra={"email": req.email, "ip": request.client.host if request.client else "unknown"})
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

    logger.info("login_success", extra={"email": req.email, "ip": ip})
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: Annotated[User, Depends(require_auth)]) -> UserResponse:
    return UserResponse.model_validate(user)
