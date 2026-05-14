"""Alpha signal endpoints — Pro tier only.

Endpoints:
    GET /alpha/nba/predictions/today  — Today's NBA predictions (with calibration)
    GET /alpha/stocks/edge/{stock_id} — Stock sharp detector edge (T8)

The sports-prophet pipeline is reached via the `fetch_nba_predictions_today`
indirection so tests can patch it. Production wiring (sports-prophet as a
service) lives outside this module.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.tier_guard import require_tier
from app.models.enums import UserTier
from app.models.user import User

router = APIRouter(prefix="/alpha", tags=["alpha"])

ProUser = Annotated[User, Depends(require_tier(UserTier.PRO))]


# ---------------------------------------------------------------------------
# Stub: sports-prophet integration deferred to production wiring task.
# ---------------------------------------------------------------------------

async def fetch_nba_predictions_today() -> list[dict[str, Any]]:
    """Return today's NBA predictions from the sports-prophet pipeline.

    In production this will run NbaXGBoostModel + ProbabilityCalibrator +
    SharpDetector and return calibrated probabilities. The stub returns
    an empty list so the endpoint is operationally safe before wiring.
    """
    return []


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class NbaPredictionItem(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    win_probability: float
    calibrated: bool
    predicted_spread: float
    sharp_signal: str          # "sharp" | "square" | "neutral"
    sharp_side: str | None
    confidence_tier: str       # "HIGH" | "MEDIUM" | "LOW"


class NbaPredictionsResponse(BaseModel):
    date: str
    tier: str
    predictions: list[NbaPredictionItem]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/nba/predictions/today", response_model=NbaPredictionsResponse)
async def get_nba_predictions_today(user: ProUser) -> NbaPredictionsResponse:
    """Today's NBA predictions with calibrated win probabilities. Pro only."""
    today = date.today().isoformat()
    raw = await fetch_nba_predictions_today()
    items = [NbaPredictionItem(**item) for item in raw]
    return NbaPredictionsResponse(date=today, tier="pro", predictions=items)
