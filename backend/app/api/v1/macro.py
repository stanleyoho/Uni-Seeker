"""Macro-level market overview API: Buffett indicator + market temperature.

These two endpoints feed the home-page mini-widget row (above the KPI tiles).
Both endpoints are intentionally cheap — they reuse existing aggregates from
``app.models.price`` and ``app.models.stock`` so adding them does NOT change
the DB shape or add a new sync job.

v1 limitations (called out in docstrings + response fields so the frontend can
render an "approximate" disclaimer):

- Buffett Indicator's GDP figure is a hardcoded snapshot. Quarterly refresh
  from 行政院主計處 would belong in a separate scheduled sync job; for v1 we
  ship a constant + emit ``gdp_source`` so the disclaimer is honest.
- Market Temperature uses *only* average change_percent across the index
  basket. The full formula (RSI + advance/decline + volume vs 20-day MA)
  needs a wider read of the price history; reserved for v2.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.cache import cache_get, cache_set, make_cache_key
from app.models.price import StockPrice
from app.models.stock import Stock
from app.schemas.macro import (
    BuffettIndicatorResponse,
    BuffettLabel,
    MarketTemperatureResponse,
    TemperatureLabel,
)

MACRO_CACHE_TTL = 300  # 5 minutes — same cadence as /market/*

# ── Hardcoded v1 fallbacks ──────────────────────────────────────────────────
#
# Taiwan nominal GDP — 2025 estimate from 行政院主計處 (約 TWD 25.5 兆).
# Stored in NTD so it can be directly compared with TWSE total market cap.
# When the v2 sync job lands, replace this constant with the latest value
# from MOF / 主計處. The unit (兆 / trillion NTD) is documented to stop a
# future contributor from accidentally swapping in a USD figure.
_TW_GDP_FALLBACK_NTD = Decimal("25_500_000_000_000")  # 25.5 兆 NTD
_TW_GDP_SOURCE = "行政院主計處 2025 估算 (hardcoded v1)"

# TWSE total market cap fallback — ~TWD 75 兆 (rough 2025 ballpark).
# Used when the DB hasn't been synced and we can't sum live market caps.
# Yields ~294% — comfortably in the "極度高估" bucket, which matches the
# real-world reading and lets the demo tile render the most interesting state.
_TWSE_MARKET_CAP_FALLBACK_NTD = Decimal("75_000_000_000_000")
_MARKET_CAP_LIVE_SOURCE = "Σ(close × shares_outstanding) latest trading day"
_MARKET_CAP_FALLBACK_SOURCE = "hardcoded v1 fallback (≈ TWD 75 兆)"

# Indices basket for temperature averaging — same set the KPI row picks
# from, so the gauge reads "what the home-page top tiles average to".
_TEMPERATURE_INDEX_SYMBOLS = (
    "^TWII",
    "^TPEX",
    "^IXIC",
    "^DJI",
    "^GSPC",
    "SPY",
    "QQQ",
    "DIA",
    "0050.TW",
)

# Average-change → score linear mapping bounds. `-3% → 0`, `+3% → 100`,
# clamped at both ends. Keeps the gauge needle moving inside each bucket.
_TEMP_LO_PCT = Decimal("-3")
_TEMP_HI_PCT = Decimal("3")

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/macro", tags=["macro"])


# ── Helpers ────────────────────────────────────────────────────────────────


def _classify_buffett(ratio_pct: Decimal) -> tuple[BuffettLabel, bool]:
    """Return (label, historical_extreme) for a Buffett ratio in percent."""
    if ratio_pct >= Decimal("200"):
        return "極度高估", True
    if ratio_pct >= Decimal("150"):
        return "高估", False
    if ratio_pct >= Decimal("75"):
        return "合理", False
    if ratio_pct >= Decimal("50"):
        return "低估", False
    return "極度低估", True


def _classify_temperature(avg_pct: Decimal) -> TemperatureLabel:
    """≤-1% → 冷, ≥+1% → 熱, else 正常."""
    if avg_pct <= Decimal("-1"):
        return "冷"
    if avg_pct >= Decimal("1"):
        return "熱"
    return "正常"


def _temperature_score(avg_pct: Decimal) -> Decimal:
    """Map average %Δ ∈ [-3, +3] linearly to [0, 100], clamped."""
    clamped = max(_TEMP_LO_PCT, min(_TEMP_HI_PCT, avg_pct))
    # (avg - lo) / (hi - lo) * 100
    span = _TEMP_HI_PCT - _TEMP_LO_PCT
    return ((clamped - _TEMP_LO_PCT) / span) * Decimal("100")


def _today_taipei() -> str:
    return str(datetime.now(tz=ZoneInfo("Asia/Taipei")).date())


# ── /macro/buffett-indicator ───────────────────────────────────────────────


@router.get("/buffett-indicator")
async def get_buffett_indicator(db: DbSession) -> BuffettIndicatorResponse:
    """台股總市值 / 台灣 GDP × 100%.

    v1: live market-cap sum when possible (joins ``stocks.shares_outstanding``
    × ``stock_prices.close`` on the latest trading day for TW markets);
    fallback to a hardcoded estimate otherwise. GDP is a hardcoded snapshot
    (see module-level constants).
    """
    cache_key = make_cache_key("macro:buffett")
    cached = await cache_get(cache_key)
    if cached:
        return BuffettIndicatorResponse(**cached)

    # Attempt to derive live TWSE market cap. The Stock model may or may not
    # carry `shares_outstanding` depending on which sync ran last; we guard
    # with getattr so a missing column doesn't 500 the home page.
    market_cap: Decimal | None = None
    market_cap_source = _MARKET_CAP_FALLBACK_SOURCE
    source_date = _today_taipei()

    shares_col = getattr(Stock, "shares_outstanding", None)
    if shares_col is not None:
        latest_date_q = (
            select(func.max(StockPrice.date))
            .join(Stock, Stock.id == StockPrice.stock_id)
            .where(Stock.market.in_(("TW_TWSE", "TW_TPEX")))
        )
        latest_date_res = await db.execute(latest_date_q)
        latest_date = latest_date_res.scalar()

        if latest_date is not None:
            cap_q = (
                select(func.sum(StockPrice.close * shares_col))
                .join(Stock, Stock.id == StockPrice.stock_id)
                .where(Stock.market.in_(("TW_TWSE", "TW_TPEX")))
                .where(StockPrice.date == latest_date)
            )
            cap_res = await db.execute(cap_q)
            raw = cap_res.scalar()
            if raw is not None:
                try:
                    candidate = Decimal(str(raw))
                except Exception:
                    candidate = Decimal("0")
                # Reject obvious garbage (sub-trillion) — likely missing
                # shares_outstanding data — and stay on the fallback path.
                if candidate >= Decimal("1_000_000_000_000"):  # ≥ 1 兆
                    market_cap = candidate
                    market_cap_source = _MARKET_CAP_LIVE_SOURCE
                    source_date = str(latest_date)

    if market_cap is None:
        market_cap = _TWSE_MARKET_CAP_FALLBACK_NTD

    ratio_pct = (market_cap / _TW_GDP_FALLBACK_NTD) * Decimal("100")
    # Quantize for stable JSON output — two decimals matches the UI rendering.
    ratio_pct = ratio_pct.quantize(Decimal("0.01"))
    label, extreme = _classify_buffett(ratio_pct)

    response = BuffettIndicatorResponse(
        ratio=ratio_pct,
        label=label,
        historical_extreme=extreme,
        source_date=source_date,
        gdp_source=_TW_GDP_SOURCE,
        market_cap_source=market_cap_source,
    )
    await cache_set(cache_key, json.loads(response.model_dump_json()), ttl=MACRO_CACHE_TTL)
    return response


# ── /macro/market-temperature ──────────────────────────────────────────────


@router.get("/market-temperature")
async def get_market_temperature(db: DbSession) -> MarketTemperatureResponse:
    """Average change_percent across the index basket → cold/normal/hot bucket.

    v1 derivation only uses *today's* change for each index proxy (the same
    set the KPI row picks from). v2 will blend RSI + advance/decline +
    volume vs 20-day MA — reserved for when the price history sync is
    locked-in across both TW and US markets.
    """
    cache_key = make_cache_key("macro:temperature")
    cached = await cache_get(cache_key)
    if cached:
        return MarketTemperatureResponse(**cached)

    # Pull the latest change_percent for each index proxy symbol. We do this
    # with a single query + post-group dedup (per-symbol latest row), so we
    # avoid N round-trips for the 9-element basket.
    latest_per_symbol_q = (
        select(
            Stock.symbol,
            StockPrice.change_percent,
            StockPrice.date,
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .where(Stock.symbol.in_(_TEMPERATURE_INDEX_SYMBOLS))
        .where(StockPrice.change_percent.isnot(None))
        .order_by(Stock.symbol, StockPrice.date.desc())
    )
    rows = (await db.execute(latest_per_symbol_q)).all()

    # Keep only the most recent row per symbol (the ORDER BY ensures the
    # first seen row for each symbol is the latest).
    seen: set[str] = set()
    latest_changes: list[Decimal] = []
    latest_date: str | None = None
    for row in rows:
        if row.symbol in seen:
            continue
        seen.add(row.symbol)
        try:
            latest_changes.append(Decimal(str(row.change_percent)))
        except Exception:
            continue
        if latest_date is None and row.date is not None:
            latest_date = str(row.date)

    # Demo fallback — when no index data is in the DB, ship a "normal" reading
    # (avg = 0) so the home page never breaks. Matches the /market/indices
    # behavior of falling back to ``_demo_indices``.
    if not latest_changes:
        average = Decimal("0")
        index_count = 0
        latest_date = _today_taipei()
    else:
        # Mean over the populated set, two-decimal quantize.
        average = (sum(latest_changes) / Decimal(len(latest_changes))).quantize(Decimal("0.01"))
        index_count = len(latest_changes)

    score = _temperature_score(average).quantize(Decimal("0.01"))
    label = _classify_temperature(average)

    response = MarketTemperatureResponse(
        score=score,
        label=label,
        average_change_percent=average,
        source_date=latest_date or _today_taipei(),
        index_count=index_count,
    )
    await cache_set(cache_key, json.loads(response.model_dump_json()), ttl=MACRO_CACHE_TTL)
    return response
