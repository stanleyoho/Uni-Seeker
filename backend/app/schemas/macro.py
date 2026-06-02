"""Macro-level market overview schemas: Buffett indicator, market temperature.

These power the home-page mini-widget row (Buffett Indicator tile + Market
Temperature Gauge). Field types follow the Decimal-as-string contract used
elsewhere in the project — frontend coerces with ``Number()`` before display.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.types import DecimalStr

# ── Buffett Indicator ───────────────────────────────────────────────────────
#
# Formula: (台股總市值 / 台灣 GDP) × 100 %.
# Buckets (Buffett's own boundaries adapted to TW):
#   <50%   → 極度低估
#   50-75% → 低估
#   75-150% → 合理
#   150-200% → 高估
#   >200%  → 極度高估
# `historical_extreme` flips true at the outer two buckets (>=200 or <=50)
# so the UI can flash an attention chip without re-computing thresholds.

BuffettLabel = Literal["極度低估", "低估", "合理", "高估", "極度高估"]


class BuffettIndicatorResponse(BaseModel):
    ratio: DecimalStr
    label: BuffettLabel
    historical_extreme: bool
    source_date: str
    # v1 derivation provenance: the GDP source defaults to a hardcoded
    # quarterly snapshot (行政院主計處) — surfaced so the frontend can
    # render a small "v1 stub" disclaimer in the tooltip.
    gdp_source: str
    market_cap_source: str


# ── Market Temperature Gauge ────────────────────────────────────────────────
#
# v1 simplified formula: average index basket change_percent → bucket into:
#   ≤ -1%  → 冷  (score 0-33)
#   -1 .. +1% → 正常 (score 34-66)
#   ≥ +1%  → 熱  (score 67-100)
# The score is linearly mapped from average_change_percent ∈ [-3, +3] to
# [0, 100] so the gauge needle has a continuous position even inside a
# bucket. Frontend renders a cold-blue → hot-red gradient bar.

TemperatureLabel = Literal["冷", "正常", "熱"]


class MarketTemperatureResponse(BaseModel):
    score: DecimalStr  # 0-100
    label: TemperatureLabel
    average_change_percent: DecimalStr
    source_date: str
    # Number of indices used in the average — lets the UI show a "based on N
    # indices" note for transparency.
    index_count: int
