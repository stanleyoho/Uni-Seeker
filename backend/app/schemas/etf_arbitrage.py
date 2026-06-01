"""Pydantic response schemas for /api/v1/etf-arbitrage/* endpoints.

The shapes here are the wire contract — the frontend types are
generated from these via the schema.d.ts pipeline. Decimal-as-string
is enforced through plain ``str`` fields because the service has
already pre-formatted +/- signed strings (e.g. "+1.41").
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ETFArbitrageRowSchema(BaseModel):
    symbol: str = Field(..., description="ETF symbol without market suffix, e.g. '00830'")
    name: str
    type: str = Field(..., description="股票型 / 主動式 / 債券型 / 槓桿反向")
    estimated_nav: str = Field(..., description="預估淨值 (Decimal as string)")
    market_price: str
    change: str = Field(..., description="Signed Decimal string, e.g. '+0.50'")
    change_percent: str
    premium_percent: str = Field(
        ..., description="(market_price - nav) / nav * 100, signed, e.g. '+1.41'"
    )
    sentiment_level: str = Field(..., description="One of: 過熱 / 溢價 / 平價 / 折價 / 深折")
    volume_lots: int = Field(..., description="Trading volume in lots (千股)")
    trend: str | None = Field(None, description="Reserved for ▲▲▲ trend rendering")


class ETFArbitrageKpiSchema(BaseModel):
    symbol: str
    name: str
    percent: str


class ETFArbitrageStatsSchema(BaseModel):
    total_monitored: int
    premium_count: int
    discount_count: int
    max_premium_etf: ETFArbitrageKpiSchema | None = None
    max_discount_etf: ETFArbitrageKpiSchema | None = None
    market_sentiment: str
    buffett_indicator: str
    data_source: str


class ETFArbitrageListResponse(BaseModel):
    data: list[ETFArbitrageRowSchema]
    stats: ETFArbitrageStatsSchema
    message: str | None = Field(
        None,
        description=(
            "Non-null when NAV data is unavailable (FinMind tier limit, "
            "pre-market). UI should render an explanatory empty state."
        ),
    )
