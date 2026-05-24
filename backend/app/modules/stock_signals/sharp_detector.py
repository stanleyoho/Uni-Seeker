"""StockSharpDetector — port of sports-prophet SharpDetector to TW stocks.

Analogy mapping:
    Pinnacle (sharp bookmaker)   -> Foreign futures net position (institutional)
    Public odds (square money)   -> Margin balance change (retail sentiment)

When institutional direction != retail direction, divergence is detected
and the signal recommends following the institutional side with boosted
confidence.

Lives in app.modules (application layer), not shared engine, because the
analogy is specific to the TW stock market dataset (FinMind futures +
TWSE margin balance). The general ML utilities live in
adaptive-alpha-engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

# Tunable thresholds — derived from historical noise floor of TW data
INSTITUTIONAL_THRESHOLD = 500.0   # foreign futures contracts (口數)
RETAIL_THRESHOLD = 5.0             # margin balance change (億元)

Direction = Literal["long", "short", "neutral"]


@dataclass(frozen=True)
class StockSharpSignal:
    institutional_direction: Direction
    retail_direction: Direction
    divergence_detected: bool
    foreign_futures_net: float
    margin_balance_change: float


@dataclass(frozen=True)
class EdgeSignal:
    stock_id: str
    date: date
    direction: Direction
    confidence: float
    divergence_detected: bool
    reason: str


class StockSharpDetector:
    """Detect smart-money vs retail divergence in the stock market.

    Two usage modes:
      1. Stateless — call ``detect_divergence(ff_net, mb_change)`` directly.
      2. Seeded — pass pre-fetched values in the constructor so
         ``get_edge_signal(stock_id, date)`` can compose a full signal
         without touching a real data source (handy in tests / mocking).

    Production wiring: ``alpha`` API constructs a fresh detector per call,
    seeded with values fetched from FinMind + TWSE margin balance.
    """

    def __init__(
        self,
        foreign_futures_net: float | None = None,
        margin_balance_change: float | None = None,
    ) -> None:
        self._seeded_ff = foreign_futures_net
        self._seeded_mb = margin_balance_change

    def detect_divergence(
        self,
        foreign_futures_net: float,
        margin_balance_change: float,
    ) -> StockSharpSignal:
        inst_dir = self._classify_institutional(foreign_futures_net)
        retail_dir = self._classify_retail(margin_balance_change)
        divergence = (
            inst_dir != "neutral"
            and retail_dir != "neutral"
            and inst_dir != retail_dir
        )
        return StockSharpSignal(
            institutional_direction=inst_dir,
            retail_direction=retail_dir,
            divergence_detected=divergence,
            foreign_futures_net=foreign_futures_net,
            margin_balance_change=margin_balance_change,
        )

    def get_edge_signal(self, stock_id: str, date: date) -> EdgeSignal:
        ff = self._seeded_ff if self._seeded_ff is not None else 0.0
        mb = self._seeded_mb if self._seeded_mb is not None else 0.0

        sharp = self.detect_divergence(ff, mb)

        if sharp.divergence_detected:
            direction = sharp.institutional_direction
            confidence = min(0.5 + abs(ff) / 40000.0, 0.9)
            reason = (
                f"法人期貨淨部位 {ff:+,.0f} 口（{direction}），"
                f"融資餘額變化 {mb:+.1f} 億，方向相反（divergence=True）。"
                f"跟隨法人方向，信心度 {confidence:.0%}。"
            )
        else:
            direction = "neutral"
            confidence = 0.0
            reason = (
                f"法人期貨淨部位 {ff:+,.0f} 口，融資餘額變化 {mb:+.1f} 億，"
                f"無 institutional/retail divergence，無明確 edge 信號。"
            )

        return EdgeSignal(
            stock_id=stock_id,
            date=date,
            direction=direction,
            confidence=round(confidence, 4),
            divergence_detected=sharp.divergence_detected,
            reason=reason,
        )

    def _classify_institutional(self, net: float) -> Direction:
        if net > INSTITUTIONAL_THRESHOLD:
            return "long"
        if net < -INSTITUTIONAL_THRESHOLD:
            return "short"
        return "neutral"

    def _classify_retail(self, change: float) -> Direction:
        if change > RETAIL_THRESHOLD:
            return "long"
        if change < -RETAIL_THRESHOLD:
            return "short"
        return "neutral"
