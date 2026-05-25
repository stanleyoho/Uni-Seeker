"""Chip-data (籌碼面) based trading strategies.

These strategies consume institutional, margin, and shareholding data
passed as keyword arguments from the BacktestEngine.
"""

from __future__ import annotations

from typing import Any

from app.modules.strategy.base import Signal, StrategyConfig


class InstitutionalFollowStrategy:
    """Buy when foreign investors or investment trusts have net-buy for N consecutive days."""

    def __init__(self, days: int = 3, investor_type: str = "Foreign_Investor") -> None:
        self.config = StrategyConfig(
            name="Institutional Follow (法人連買)",
            description=f"Net-buy for {days} consecutive days by {investor_type}",
            params={"days": days, "investor_type": investor_type},
        )
        self._days = days
        self._investor_type = investor_type
        self._history: list[float] = []  # net buy amounts per day

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        institutional: list[dict[str, Any]] = kwargs.get("institutional", [])  # type: ignore[assignment]

        # Compute net buy for the investor type on this day
        net_buy = 0.0
        for rec in institutional:
            if rec.get("name") == self._investor_type:
                net_buy = float(rec.get("buy", 0)) - float(rec.get("sell", 0))
                break

        self._history.append(net_buy)

        if len(self._history) < self._days:
            return Signal(action="HOLD", symbol="", reason="Insufficient chip history")

        recent = self._history[-self._days :]

        if all(v > 0 for v in recent):
            strength = min(sum(recent) / (self._days * 1000), 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"{self._investor_type} net-buy for {self._days} consecutive days",
                strength=max(strength, 0.5),
            )
        elif all(v < 0 for v in recent):
            strength = min(abs(sum(recent)) / (self._days * 1000), 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"{self._investor_type} net-sell for {self._days} consecutive days",
                strength=max(strength, 0.5),
            )

        return Signal(
            action="HOLD", symbol="", reason=f"{self._investor_type} no consecutive trend"
        )


class MarginDivergenceStrategy:
    """Contrarian: Buy when margin balance decreases AND short selling
    increases (retail bearish)."""

    def __init__(self, lookback: int = 5) -> None:
        self.config = StrategyConfig(
            name="Margin Divergence (融資融券背離)",
            description=f"Margin balance vs short sale divergence over {lookback} days",
            params={"lookback": lookback},
        )
        self._lookback = lookback
        self._margin_history: list[float] = []
        self._short_history: list[float] = []

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        margin_list: list[dict[str, Any]] = kwargs.get("margin", [])  # type: ignore[assignment]

        margin_balance = 0.0
        short_balance = 0.0
        for rec in margin_list:
            margin_balance = float(rec.get("MarginPurchaseTodayBalance", 0))
            short_balance = float(rec.get("ShortSaleTodayBalance", 0))

        self._margin_history.append(margin_balance)
        self._short_history.append(short_balance)

        if len(self._margin_history) < self._lookback + 1:
            return Signal(action="HOLD", symbol="", reason="Insufficient margin history")

        recent_margin = self._margin_history[-(self._lookback + 1) :]
        recent_short = self._short_history[-(self._lookback + 1) :]

        margin_trend = recent_margin[-1] - recent_margin[0]
        short_trend = recent_short[-1] - recent_short[0]

        # Contrarian: retail fear = opportunity
        if margin_trend < 0 and short_trend > 0:
            strength = min(abs(margin_trend) / (abs(margin_trend) + abs(short_trend) + 1), 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=(
                    f"Margin down {margin_trend:.0f}, short up {short_trend:.0f} (retail bearish)"
                ),
                strength=max(strength, 0.5),
            )
        # Retail FOMO = danger
        elif margin_trend > 0 and abs(margin_trend) > abs(short_trend) * 2:
            strength = min(margin_trend / (margin_trend + abs(short_trend) + 1), 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"Margin surging up {margin_trend:.0f} (retail FOMO)",
                strength=max(strength, 0.5),
            )

        return Signal(action="HOLD", symbol="", reason="No margin divergence signal")


class ForeignTrustSyncStrategy:
    """Strong Buy when both foreign investors AND investment trusts are net buyers on same day."""

    def __init__(self, min_net_buy: int = 0) -> None:
        self.config = StrategyConfig(
            name="Foreign + Trust Sync (外資投信同步)",
            description="Buy when both foreign and trust are net buyers",
            params={"min_net_buy": min_net_buy},
        )
        self._min_net_buy = min_net_buy

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        institutional: list[dict[str, Any]] = kwargs.get("institutional", [])  # type: ignore[assignment]

        foreign_net = 0.0
        trust_net = 0.0
        for rec in institutional:
            name = rec.get("name", "")
            buy = float(rec.get("buy", 0))
            sell = float(rec.get("sell", 0))
            if name == "Foreign_Investor":
                foreign_net = buy - sell
            elif name == "Investment_Trust":
                trust_net = buy - sell

        if foreign_net > self._min_net_buy and trust_net > self._min_net_buy:
            combined = foreign_net + trust_net
            strength = min(combined / (combined + 10000), 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"Foreign net +{foreign_net:.0f}, Trust net +{trust_net:.0f} (sync buy)",
                strength=max(strength, 0.6),
            )
        elif foreign_net < -self._min_net_buy and trust_net < -self._min_net_buy:
            combined = abs(foreign_net) + abs(trust_net)
            strength = min(combined / (combined + 10000), 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"Foreign net {foreign_net:.0f}, Trust net {trust_net:.0f} (sync sell)",
                strength=max(strength, 0.6),
            )

        return Signal(action="HOLD", symbol="", reason="Foreign and trust not in sync")


class OwnershipConcentrationStrategy:
    """Buy when foreign ownership ratio has been increasing for N consecutive periods."""

    def __init__(self, days: int = 5) -> None:
        self.config = StrategyConfig(
            name="Ownership Concentration (股權集中度)",
            description=f"Foreign ownership ratio increasing for {days} days",
            params={"days": days},
        )
        self._days = days
        self._ratio_history: list[float] = []

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        shareholding: list[dict[str, Any]] = kwargs.get("shareholding", [])  # type: ignore[assignment]

        ratio = 0.0
        for rec in shareholding:
            val = rec.get("ForeignInvestmentSharesRatio", 0)
            if val:
                ratio = float(val)

        self._ratio_history.append(ratio)

        if len(self._ratio_history) < self._days + 1:
            return Signal(action="HOLD", symbol="", reason="Insufficient ownership history")

        recent = self._ratio_history[-(self._days + 1) :]

        # Check if ratio has been increasing for N consecutive days
        increasing = all(recent[i + 1] > recent[i] for i in range(self._days))
        decreasing = all(recent[i + 1] < recent[i] for i in range(self._days))

        if increasing:
            change = recent[-1] - recent[0]
            strength = min(change / 5.0, 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=(
                    f"Foreign ownership ratio increasing {self._days} days "
                    f"({recent[0]:.2f}% -> {recent[-1]:.2f}%)"
                ),
                strength=max(strength, 0.5),
            )
        elif decreasing:
            change = recent[0] - recent[-1]
            strength = min(change / 5.0, 1.0)
            return Signal(
                action="SELL",
                symbol="",
                reason=(
                    f"Foreign ownership ratio decreasing {self._days} days "
                    f"({recent[0]:.2f}% -> {recent[-1]:.2f}%)"
                ),
                strength=max(strength, 0.5),
            )

        return Signal(action="HOLD", symbol="", reason="Ownership ratio no clear trend")


class MarginOverleverageStrategy:
    """Sell when margin utilization rate exceeds threshold (overleveraged)."""

    def __init__(self, sell_threshold: float = 80.0, buy_threshold: float = 30.0) -> None:
        self.config = StrategyConfig(
            name="Margin Overleverage (融資使用率)",
            description=f"Sell when margin util > {sell_threshold}%, buy when < {buy_threshold}%",
            params={"sell_threshold": sell_threshold, "buy_threshold": buy_threshold},
        )
        self._sell_threshold = sell_threshold
        self._buy_threshold = buy_threshold

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        margin_list: list[dict[str, Any]] = kwargs.get("margin", [])  # type: ignore[assignment]

        utilization = -1.0
        for rec in margin_list:
            balance = float(rec.get("MarginPurchaseTodayBalance", 0))
            limit = float(rec.get("MarginPurchaseLimit", 0))
            if limit > 0:
                utilization = balance / limit * 100

        if utilization < 0:
            return Signal(action="HOLD", symbol="", reason="No margin utilization data")

        if utilization > self._sell_threshold:
            strength = min(
                (utilization - self._sell_threshold) / (100 - self._sell_threshold + 1), 1.0
            )
            return Signal(
                action="SELL",
                symbol="",
                reason=(
                    f"Margin utilization {utilization:.1f}% > "
                    f"{self._sell_threshold}% (overleveraged)"
                ),
                strength=max(strength, 0.5),
            )
        elif utilization < self._buy_threshold:
            strength = min((self._buy_threshold - utilization) / self._buy_threshold, 1.0)
            return Signal(
                action="BUY",
                symbol="",
                reason=(
                    f"Margin utilization {utilization:.1f}% < {self._buy_threshold}% (deleveraged)"
                ),
                strength=max(strength, 0.5),
            )

        return Signal(
            action="HOLD",
            symbol="",
            reason=f"Margin utilization {utilization:.1f}% in neutral range",
        )
