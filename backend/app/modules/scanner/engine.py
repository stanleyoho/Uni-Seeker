"""Signal scanner engine -- pure computation, no DB dependency."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.strategy.base import Signal
from app.modules.strategy.registry import StrategyRegistry


@dataclass
class StockSignal:
    """Aggregated signal result for a single stock."""

    symbol: str
    name: str
    signals: list[dict[str, object]] = field(default_factory=list)
    composite_action: str = "HOLD"
    score: float = 0.0


def _action_to_score(action: str, strength: float) -> float:
    """Map a single signal action+strength to a numeric score."""
    if action == "BUY":
        return strength
    if action == "SELL":
        return -strength
    return 0.0


def _score_to_action(score: float) -> str:
    """Map a composite score to an action label."""
    if score > 0.5:
        return "STRONG_BUY"
    if score > 0.1:
        return "BUY"
    if score > -0.1:
        return "HOLD"
    if score > -0.5:
        return "SELL"
    return "STRONG_SELL"


class SignalScanner:
    """Run registered strategies against stock price data and aggregate signals.

    This class is intentionally DB-free: it accepts raw price lists so that
    it can be unit-tested without any infrastructure.
    """

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def scan_stock(
        self,
        symbol: str,
        name: str,
        closes: list[float],
        strategy_keys: list[str] | None = None,
    ) -> StockSignal:
        """Scan a single stock with all (or specified) strategies.

        Parameters
        ----------
        symbol:
            Stock ticker, e.g. ``"2330"``.
        name:
            Human-readable stock name, e.g. ``"台積電"``.
        closes:
            Chronologically ordered closing prices (oldest first).
        strategy_keys:
            Subset of registered strategy keys to evaluate.  ``None`` means
            *all* registered strategies.

        Returns
        -------
        StockSignal
            Aggregated result with per-strategy details and a composite score.
        """
        keys = strategy_keys or self._registry.list_keys()
        signal_details: list[dict[str, object]] = []
        scores: list[float] = []

        for key in keys:
            strategy = self._registry.get(key)
            signal: Signal = strategy.evaluate(closes)

            detail: dict[str, object] = {
                "strategy": key,
                "action": signal.action,
                "strength": signal.strength,
                "reason": signal.reason,
            }
            signal_details.append(detail)
            scores.append(_action_to_score(signal.action, signal.strength))

        composite = sum(scores) / len(scores) if scores else 0.0

        return StockSignal(
            symbol=symbol,
            name=name,
            signals=signal_details,
            composite_action=_score_to_action(composite),
            score=round(composite, 4),
        )

    def scan_many(
        self,
        stocks_data: list[dict[str, object]],
        strategy_keys: list[str] | None = None,
    ) -> list[StockSignal]:
        """Scan multiple stocks, returning results sorted by score descending.

        Parameters
        ----------
        stocks_data:
            Each dict must contain ``"symbol"`` (str), ``"name"`` (str), and
            ``"closes"`` (list[float]).
        strategy_keys:
            Optional subset of strategy keys.

        Returns
        -------
        list[StockSignal]
            Results ordered from highest (most bullish) to lowest score.
        """
        results: list[StockSignal] = []
        for stock in stocks_data:
            symbol: str = stock["symbol"]  # type: ignore[assignment]
            name: str = stock["name"]  # type: ignore[assignment]
            closes: list[float] = stock["closes"]  # type: ignore[assignment]

            if len(closes) < 2:
                continue

            result = self.scan_stock(symbol, name, closes, strategy_keys)
            results.append(result)

        results.sort(key=lambda r: r.score, reverse=True)
        return results
