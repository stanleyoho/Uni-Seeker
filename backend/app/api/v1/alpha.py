"""Alpha signal endpoints — Pro tier only.

Endpoints:
    GET /alpha/nba/predictions/today  — Today's NBA predictions (with calibration)
    GET /alpha/stocks/edge/{stock_id} — Stock sharp detector edge (T8)

The sports-prophet pipeline is reached via the `fetch_nba_predictions_today`
indirection so tests can patch it. Production wiring (sports-prophet as a
service) lives outside this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

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
    sharp_signal: str  # "sharp" | "square" | "neutral"
    sharp_side: str | None
    confidence_tier: str  # "HIGH" | "MEDIUM" | "LOW"


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
    today = datetime.now(tz=UTC).date().isoformat()
    raw = await fetch_nba_predictions_today()
    items = [NbaPredictionItem(**item) for item in raw]
    return NbaPredictionsResponse(date=today, tier="pro", predictions=items)


# ---------------------------------------------------------------------------
# Stock edge stub — production wiring fetches foreign futures + margin data.
# ---------------------------------------------------------------------------

from app.modules.stock_signals.sharp_detector import (
    EdgeSignal,
    StockSharpDetector,
)


async def fetch_stock_edge_signal(stock_id: str) -> EdgeSignal:
    """Compose a StockSharpDetector edge signal for the given stock.

    Production: fetch foreign_futures_net from FinMind / TWSE and
    margin_balance_change from margin data provider. Stub seeds the
    detector with zeros so the endpoint is operationally safe before
    the data wiring lands.
    """
    detector = StockSharpDetector()
    return detector.get_edge_signal(
        stock_id=stock_id,
        date=datetime.now(tz=ZoneInfo("Asia/Taipei")).date(),
    )


class StockEdgeResponse(BaseModel):
    stock_id: str
    date: str
    direction: str  # "long" | "short" | "neutral"
    confidence: float
    divergence_detected: bool
    reason: str
    tier: str


@router.get("/stocks/edge/{stock_id}", response_model=StockEdgeResponse)
async def get_stock_edge_signal(
    stock_id: str,
    user: ProUser,
) -> StockEdgeResponse:
    """Institutional vs retail divergence edge signal for a stock. Pro only.

    Logic lives in StockSharpDetector. CompliancePurifier middleware will
    rewrite any investment-advice phrasing in the `reason` field before
    the response reaches the client.
    """
    edge = await fetch_stock_edge_signal(stock_id)
    return StockEdgeResponse(
        stock_id=edge.stock_id,
        date=edge.date.isoformat(),
        direction=edge.direction,
        confidence=edge.confidence,
        divergence_detected=edge.divergence_detected,
        reason=edge.reason,
        tier="pro",
    )
