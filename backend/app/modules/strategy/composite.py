from app.modules.strategy.base import Signal, Strategy, StrategyConfig


class CompositeStrategy:
    """Combine multiple strategies with configurable voting logic.

    Modes:
        - "all":      ALL sub-strategies must agree (AND logic, strictest)
        - "any":      ANY sub-strategy triggers (OR logic, most sensitive)
        - "majority": Majority vote decides (balanced)
    """

    def __init__(
        self,
        strategies: list[Strategy],
        mode: str = "majority",
        name: str | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("CompositeStrategy requires at least one sub-strategy")
        if mode not in ("all", "any", "majority"):
            raise ValueError(f"Invalid mode '{mode}'. Must be 'all', 'any', or 'majority'")

        self._strategies = strategies
        self._mode = mode
        sub_names = " + ".join(s.config.name for s in strategies)
        self.config = StrategyConfig(
            name=name or f"Composite({sub_names})",
            description=f"[{mode}] {sub_names}",
            params={"mode": mode, "sub_strategies": [s.config.name for s in strategies]},
        )

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        signals = [s.evaluate(closes, **kwargs) for s in self._strategies]

        buy_signals = [s for s in signals if s.action == "BUY"]
        sell_signals = [s for s in signals if s.action == "SELL"]
        total = len(signals)

        if self._mode == "all":
            return self._eval_all(buy_signals, sell_signals, signals, total)
        elif self._mode == "any":
            return self._eval_any(buy_signals, sell_signals, signals)
        else:
            return self._eval_majority(buy_signals, sell_signals, signals, total)

    def _eval_all(
        self,
        buys: list[Signal],
        sells: list[Signal],
        all_signals: list[Signal],
        total: int,
    ) -> Signal:
        if len(buys) == total:
            reasons = [s.reason for s in buys]
            avg_strength = sum(s.strength for s in buys) / total
            return Signal(
                action="BUY",
                symbol="",
                reason=f"[ALL] {' | '.join(reasons)}",
                strength=avg_strength,
            )
        if len(sells) == total:
            reasons = [s.reason for s in sells]
            avg_strength = sum(s.strength for s in sells) / total
            return Signal(
                action="SELL",
                symbol="",
                reason=f"[ALL] {' | '.join(reasons)}",
                strength=avg_strength,
            )
        actions = [s.action for s in all_signals]
        return Signal(action="HOLD", symbol="", reason=f"[ALL] No consensus: {actions}")

    def _eval_any(
        self,
        buys: list[Signal],
        sells: list[Signal],
        all_signals: list[Signal],
    ) -> Signal:
        # BUY takes priority over SELL when both exist
        if buys:
            strongest = max(buys, key=lambda s: s.strength)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"[ANY] {strongest.reason}",
                strength=strongest.strength,
            )
        if sells:
            strongest = max(sells, key=lambda s: s.strength)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"[ANY] {strongest.reason}",
                strength=strongest.strength,
            )
        return Signal(action="HOLD", symbol="", reason="[ANY] All HOLD")

    def _eval_majority(
        self,
        buys: list[Signal],
        sells: list[Signal],
        all_signals: list[Signal],
        total: int,
    ) -> Signal:
        threshold = total / 2
        if len(buys) > threshold:
            reasons = [s.reason for s in buys]
            avg_strength = sum(s.strength for s in buys) / len(buys)
            return Signal(
                action="BUY",
                symbol="",
                reason=f"[MAJORITY {len(buys)}/{total}] {' | '.join(reasons)}",
                strength=avg_strength,
            )
        if len(sells) > threshold:
            reasons = [s.reason for s in sells]
            avg_strength = sum(s.strength for s in sells) / len(sells)
            return Signal(
                action="SELL",
                symbol="",
                reason=f"[MAJORITY {len(sells)}/{total}] {' | '.join(reasons)}",
                strength=avg_strength,
            )
        actions = [s.action for s in all_signals]
        return Signal(action="HOLD", symbol="", reason=f"[MAJORITY] No majority: {actions}")
