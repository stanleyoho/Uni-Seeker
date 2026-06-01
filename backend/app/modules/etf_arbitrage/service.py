"""Aggregator service that joins market prices and ETF NAV → arbitrage rows.

The service is deliberately *thin*. Heavy work belongs in either:

- ``classifier``  — pure logic, fast unit tests.
- ``FinMindMarketProvider.fetch_etf_nav`` — IO.

The endpoint composes this service over a list of ETF symbols from the
``stocks`` table. If NAV data is unavailable (FinMind tier limitation or
weekend / pre-market), the service returns an empty rows list and a
non-empty ``message`` so the UI can degrade gracefully instead of
fabricating numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.etf_arbitrage.classifier import (
    classify_etf_type,
    classify_sentiment,
)
from app.modules.finmind.market_provider import FinMindMarketProvider

logger = structlog.get_logger()

_TW_MARKETS: tuple[Market, ...] = (Market.TW_TWSE, Market.TW_TPEX)
_NAV_LOOKBACK_DAYS = 7


@dataclass
class ETFArbitrageRow:
    """One row in the arbitrage table (one ETF, one trading day)."""

    symbol: str
    name: str
    type: str
    estimated_nav: Decimal
    market_price: Decimal
    change: Decimal
    change_percent: Decimal
    premium_percent: Decimal
    sentiment_level: str
    volume_lots: int
    trend: str | None = None  # reserved for ▲▲▲ trend rendering

    def to_dict(self) -> dict[str, Any]:
        # Decimal-as-string contract.
        def s(v: Decimal, sign: bool = False) -> str:
            q = v.quantize(Decimal("0.01"))
            if sign and v >= 0:
                return f"+{q}"
            return str(q)

        return {
            "symbol": self.symbol,
            "name": self.name,
            "type": self.type,
            "estimated_nav": s(self.estimated_nav),
            "market_price": s(self.market_price),
            "change": s(self.change, sign=True),
            "change_percent": s(self.change_percent, sign=True),
            "premium_percent": s(self.premium_percent, sign=True),
            "sentiment_level": self.sentiment_level,
            "volume_lots": self.volume_lots,
            "trend": self.trend,
        }


@dataclass
class ETFArbitrageStats:
    """Aggregated stats shown in the top-row tiles + temperature widget."""

    total_monitored: int
    premium_count: int
    discount_count: int
    max_premium_etf: dict[str, str] | None
    max_discount_etf: dict[str, str] | None
    market_sentiment: str
    buffett_indicator: str
    data_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_monitored": self.total_monitored,
            "premium_count": self.premium_count,
            "discount_count": self.discount_count,
            "max_premium_etf": self.max_premium_etf,
            "max_discount_etf": self.max_discount_etf,
            "market_sentiment": self.market_sentiment,
            "buffett_indicator": self.buffett_indicator,
            "data_source": self.data_source,
        }


class ETFArbitrageService:
    """Compose ETF list + latest market price + latest NAV → arbitrage rows.

    The provider is injected so tests can stub FinMind without touching
    a real network. The DB session is passed per-call (request-scoped).
    """

    def __init__(self, provider: FinMindMarketProvider | None = None) -> None:
        self._provider = provider or FinMindMarketProvider()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def list_etfs(
        self,
        db: AsyncSession,
        *,
        market: str = "TW",
        type_filter: str = "all",
        direction: str = "all",
        limit: int = 50,
    ) -> tuple[list[ETFArbitrageRow], ETFArbitrageStats, str | None]:
        """Build arbitrage rows + stats for the current trading day.

        Returns
        -------
        (rows, stats, message)
            ``rows`` honors the `direction` and `type_filter` query
            parameters and is truncated to ``limit``. ``message`` is
            non-None when NAV data could not be fetched (e.g. FinMind
            tier restriction); the caller surfaces it to the client so
            the UI can render an explanatory empty state instead of
            misleading zeros.
        """
        # 1. ETF universe — anything in the Taiwan markets whose name
        #    contains "ETF". This is intentionally permissive; once a
        #    dedicated `is_etf` column lands we'll switch over.
        etf_rows = await self._load_etf_universe(db, market=market)
        if not etf_rows:
            return ([], self._empty_stats(), "No ETFs found in stocks table.")

        # 2. Latest market price per ETF — single grouped query, no N+1.
        prices = await self._load_latest_prices(db, etf_rows)

        # 3. NAV — FinMind. Best-effort: skip ETFs without data, log
        #    and continue. If ZERO ETFs come back with NAV → degrade.
        nav_map, nav_message = await self._load_nav_map(etf_rows)

        # 4. Compose rows
        rows: list[ETFArbitrageRow] = []
        for stock in etf_rows:
            price_row = prices.get(stock.id)
            nav = nav_map.get(stock.symbol)
            if price_row is None or nav is None or nav <= 0:
                continue
            try:
                premium = ((price_row.close - nav) / nav * Decimal("100")).quantize(Decimal("0.01"))
            except (InvalidOperation, ZeroDivisionError):
                continue
            etf_type = classify_etf_type(stock.name)
            sentiment = classify_sentiment(premium)
            rows.append(
                ETFArbitrageRow(
                    symbol=stock.symbol.replace(".TW", "").replace(".TWO", ""),
                    name=stock.name,
                    type=etf_type,
                    estimated_nav=nav,
                    market_price=price_row.close,
                    change=price_row.change,
                    change_percent=price_row.change_percent,
                    premium_percent=premium,
                    sentiment_level=sentiment,
                    volume_lots=int((price_row.volume or 0) // 1000),
                    trend=None,
                )
            )

        # 5. Filters + sort.
        rows = self._apply_filters(rows, type_filter=type_filter, direction=direction)
        # Default sort: by |premium%| desc so the most actionable rows
        # rise to the top — matches twetf.com default sort.
        rows.sort(key=lambda r: abs(r.premium_percent), reverse=True)
        truncated = rows[:limit]

        # 6. Stats are derived from the *unfiltered* row set so the
        #    counters reflect the full market, not the user's view.
        stats = self._build_stats(rows)

        return (truncated, stats, nav_message)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_etf_universe(
        self,
        db: AsyncSession,
        *,
        market: str,
    ) -> list[Stock]:
        # v1 only supports TW; the parameter is kept for forward-compat
        # and the same universe applies regardless of the input value.
        del market  # unused — explicit so reviewers see the intent
        markets = _TW_MARKETS
        stmt = (
            select(Stock)
            .where(Stock.market.in_(markets))
            .where(Stock.is_active.is_(True))
            .where(Stock.name.like("%ETF%"))
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _load_latest_prices(
        self,
        db: AsyncSession,
        stocks: list[Stock],
    ) -> dict[int, StockPrice]:
        """Latest StockPrice per stock_id. One query, sorted desc.

        SQL note — for tiny TW ETF universes (~310 rows) the simple
        "fetch latest 30 days, dedupe in Python" pattern is faster and
        more portable than a DISTINCT ON or window function. If the
        universe grows past 10k we'll revisit.
        """
        if not stocks:
            return {}
        ids = [s.id for s in stocks]
        cutoff = date.today() - timedelta(days=14)
        stmt = (
            select(StockPrice)
            .where(StockPrice.stock_id.in_(ids))
            .where(StockPrice.date >= cutoff)
            .order_by(StockPrice.stock_id, desc(StockPrice.date))
        )
        result = await db.execute(stmt)
        latest: dict[int, StockPrice] = {}
        for row in result.scalars().all():
            # First row per stock_id wins (DESC date).
            if row.stock_id not in latest:
                latest[row.stock_id] = row
        return latest

    async def _load_nav_map(
        self,
        stocks: list[Stock],
    ) -> tuple[dict[str, Decimal], str | None]:
        """Fetch latest NAV per ETF symbol. Returns ``(map, message)``.

        We hit FinMind once per symbol; the alternative is a single
        ``TaiwanStockNAV`` call without ``data_id`` which is not
        supported by the dataset. The for-loop is bounded by the ETF
        universe size (~hundreds), so it's tolerable behind the daily
        refresh job in production. Test stubs short-circuit it.
        """
        nav_map: dict[str, Decimal] = {}
        empty_responses = 0
        start = (date.today() - timedelta(days=_NAV_LOOKBACK_DAYS)).isoformat()
        for stock in stocks:
            symbol_id = stock.symbol.replace(".TW", "").replace(".TWO", "")
            try:
                raw = await self._provider.fetch_etf_nav(
                    stock_id=symbol_id,
                    start_date=start,
                )
            except Exception as exc:
                logger.warning(
                    "etf_arbitrage_nav_fetch_failed",
                    symbol=symbol_id,
                    error=str(exc),
                )
                continue
            if not raw:
                empty_responses += 1
                continue
            # Pick the most recent record. FinMind returns ASC by date.
            latest = raw[-1]
            nav_raw = latest.get("nav") or latest.get("estimated_nav")
            if nav_raw is None:
                continue
            try:
                nav_map[symbol_id] = Decimal(str(nav_raw))
            except (InvalidOperation, ValueError):
                continue

        message: str | None = None
        # If the universe is non-empty but no NAVs came back, surface
        # the v1 limitation cleanly. Don't return numbers.
        if stocks and not nav_map:
            message = (
                "FinMind 預估淨值資料不可用 (TaiwanStockNAV dataset 未授權或"
                "今日尚未發布)。請確認 FinMind token 權限或於 17:35 後重試。"
            )
        return nav_map, message

    def _apply_filters(
        self,
        rows: list[ETFArbitrageRow],
        *,
        type_filter: str,
        direction: str,
    ) -> list[ETFArbitrageRow]:
        out = rows
        if type_filter and type_filter != "all":
            out = [r for r in out if r.type == type_filter]
        if direction == "premium":
            out = [r for r in out if r.premium_percent > 0]
        elif direction == "discount":
            out = [r for r in out if r.premium_percent < 0]
        return out

    def _build_stats(self, rows: list[ETFArbitrageRow]) -> ETFArbitrageStats:
        total = len(rows)
        premium = sum(1 for r in rows if r.premium_percent > 0)
        discount = sum(1 for r in rows if r.premium_percent < 0)

        max_premium = max(rows, key=lambda r: r.premium_percent, default=None)
        max_discount = min(rows, key=lambda r: r.premium_percent, default=None)

        def _kpi(r: ETFArbitrageRow | None) -> dict[str, str] | None:
            if r is None:
                return None
            sign = "+" if r.premium_percent >= 0 else ""
            return {
                "symbol": r.symbol,
                "name": r.name,
                "percent": f"{sign}{r.premium_percent}",
            }

        # Market sentiment is the dominant bucket — quick heuristic that
        # matches the twetf.com header bubble.
        avg_premium = (
            sum((r.premium_percent for r in rows), Decimal("0")) / Decimal(total)
            if total
            else Decimal("0")
        )
        sentiment = classify_sentiment(avg_premium)
        # Translate to the "微幅XX" phrasing used in the reference.
        if sentiment == "溢價":
            sentiment_label = "微幅溢價"
        elif sentiment == "折價":
            sentiment_label = "微幅折價"
        else:
            sentiment_label = sentiment

        source = f"TWSE · FinMind · {date.today().isoformat()}"
        return ETFArbitrageStats(
            total_monitored=total,
            premium_count=premium,
            discount_count=discount,
            max_premium_etf=_kpi(max_premium),
            max_discount_etf=_kpi(max_discount),
            market_sentiment=sentiment_label,
            buffett_indicator="—",
            data_source=source,
        )

    def _empty_stats(self) -> ETFArbitrageStats:
        return ETFArbitrageStats(
            total_monitored=0,
            premium_count=0,
            discount_count=0,
            max_premium_etf=None,
            max_discount_etf=None,
            market_sentiment="—",
            buffett_indicator="—",
            data_source=f"TWSE · FinMind · {date.today().isoformat()}",
        )
