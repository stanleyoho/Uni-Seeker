"""Prediction Store endpoints for Uni-Seeker.

Exposes save and resolve operations for the prediction_engine package,
enabling Uni-Seeker's stock models to record and evaluate their predictions.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.obs.logging import get_logger

logger = get_logger(component="predictions")
router = APIRouter(prefix="/predictions", tags=["predictions"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SavePredictionRequest(BaseModel):
    domain: str = Field(..., pattern="^(stocks|nba)$")
    entity_id: str = Field(..., min_length=1, max_length=100)
    model_version: str = Field(..., min_length=1, max_length=50)
    prediction_value: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    shap_values: Optional[dict[str, float]] = None


class SavePredictionResponse(BaseModel):
    prediction_id: int


class ResolvePredictionRequest(BaseModel):
    actual_value: float


class ResolvePredictionResponse(BaseModel):
    prediction_id: int
    is_resolved: bool
    error: Optional[float]
    is_correct: Optional[bool]


class PerformanceResponse(BaseModel):
    total: int
    correct: int
    accuracy: Optional[float]
    avg_confidence: Optional[float]
    avg_error: Optional[float]


# ── Sync engine cache for prediction_engine's SQLite DB ──────────────────────

_PE_ENGINE = None


def _get_sync_engine():
    """Return (and lazily build) a sync SQLAlchemy engine for prediction_engine."""
    global _PE_ENGINE
    if _PE_ENGINE is None:
        from prediction_engine.models import Base
        from sqlalchemy import create_engine

        _PE_ENGINE = create_engine(
            "sqlite:///prediction_engine.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(_PE_ENGINE)
    return _PE_ENGINE


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/save", status_code=201, response_model=SavePredictionResponse)
async def save_prediction(req: SavePredictionRequest) -> SavePredictionResponse:
    """Record a new model prediction."""
    from prediction_engine.store import PredictionStore
    from sqlalchemy.orm import Session

    engine = _get_sync_engine()

    def _save() -> int:
        with Session(engine) as sess:
            store = PredictionStore(sess)
            pid = store.save_prediction(
                domain=req.domain,
                entity_id=req.entity_id,
                model_version=req.model_version,
                prediction_value=req.prediction_value,
                confidence=req.confidence,
                shap_values=req.shap_values,
            )
            sess.commit()
            return pid

    loop = asyncio.get_running_loop()
    pid = await loop.run_in_executor(None, _save)
    return SavePredictionResponse(prediction_id=pid)


@router.post(
    "/resolve/{prediction_id}",
    status_code=200,
    response_model=ResolvePredictionResponse,
)
async def resolve_prediction(
    prediction_id: int,
    req: ResolvePredictionRequest,
) -> ResolvePredictionResponse:
    """Fill in actual outcome for a previously saved prediction."""
    from prediction_engine.models import PredictionRecord
    from prediction_engine.store import PredictionStore
    from sqlalchemy.orm import Session

    engine = _get_sync_engine()

    def _resolve() -> dict[str, object]:
        with Session(engine) as sess:
            store = PredictionStore(sess)
            try:
                store.resolve_prediction(prediction_id, actual_value=req.actual_value)
                sess.commit()
            except ValueError as exc:
                msg = str(exc)
                if "not found" in msg:
                    raise
                if "already resolved" in msg:
                    raise ValueError(f"already_resolved: {msg}") from exc
                raise
            rec = sess.get(PredictionRecord, prediction_id)
            return {
                "error": rec.error if rec else None,
                "is_correct": rec.is_correct if rec else None,
            }

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, _resolve)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        if "already_resolved" in msg or "already resolved" in msg:
            raise HTTPException(
                status_code=409, detail="Prediction already resolved"
            ) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    return ResolvePredictionResponse(
        prediction_id=prediction_id,
        is_resolved=True,
        error=result["error"],  # type: ignore[arg-type]
        is_correct=result["is_correct"],  # type: ignore[arg-type]
    )


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    domain: str = Query(..., pattern="^(stocks|nba)$"),
    days: int = Query(7, ge=1, le=90),
) -> PerformanceResponse:
    """Return accuracy statistics for *domain* over the last *days* days."""
    from prediction_engine.store import PredictionStore
    from sqlalchemy.orm import Session

    engine = _get_sync_engine()

    def _query() -> dict:
        with Session(engine) as sess:
            store = PredictionStore(sess)
            return store.get_performance_window(domain=domain, days=days)

    loop = asyncio.get_running_loop()
    stats = await loop.run_in_executor(None, _query)
    return PerformanceResponse(**stats)
