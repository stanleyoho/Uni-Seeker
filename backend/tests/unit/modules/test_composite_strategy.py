"""Unit tests for `CompositeStrategy` — combines sub-strategies via
'all' / 'any' / 'majority' voting. Pure compute, no fixtures."""

from __future__ import annotations

from app.modules.strategy.base import Signal, StrategyConfig
from app.modules.strategy.composite import CompositeStrategy


class _StubStrategy:
    """Minimal Strategy implementation that returns a fixed Signal."""

    def __init__(self, action: str, strength: float = 0.5, name: str = "stub") -> None:
        self._signal = Signal(action=action, symbol="", reason=name, strength=strength)
        self.config = StrategyConfig(name=name, description=name, params={})

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        return self._signal


# ── construction guards ─────────────────────────────────────────────────


def test_composite_requires_at_least_one_strategy() -> None:
    try:
        CompositeStrategy(strategies=[])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_composite_rejects_invalid_mode() -> None:
    try:
        CompositeStrategy(strategies=[_StubStrategy("BUY")], mode="weird")
    except ValueError as exc:
        assert "Invalid mode" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_composite_default_mode_is_majority() -> None:
    cs = CompositeStrategy(strategies=[_StubStrategy("BUY")])
    assert cs._mode == "majority"


def test_composite_custom_name_used() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("BUY")], mode="all", name="CustomName"
    )
    assert cs.config.name == "CustomName"


def test_composite_auto_name_combines_subs() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("BUY", name="A"), _StubStrategy("SELL", name="B")]
    )
    assert "A + B" in cs.config.name


# ── all mode ─────────────────────────────────────────────────────────────


def test_all_mode_unanimous_buy() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("BUY", 0.6, "A"), _StubStrategy("BUY", 0.8, "B")],
        mode="all",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "BUY"
    assert "[ALL]" in sig.reason
    assert sig.strength == 0.7  # avg of 0.6 + 0.8


def test_all_mode_unanimous_sell() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("SELL", 0.5, "A"), _StubStrategy("SELL", 0.9, "B")],
        mode="all",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "SELL"
    assert sig.strength == 0.7


def test_all_mode_no_consensus_holds() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("BUY"), _StubStrategy("SELL")], mode="all"
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "HOLD"
    assert "No consensus" in sig.reason


# ── any mode ─────────────────────────────────────────────────────────────


def test_any_mode_picks_strongest_buy() -> None:
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("BUY", 0.6, "weak"),
            _StubStrategy("BUY", 0.9, "strong"),
            _StubStrategy("HOLD"),
        ],
        mode="any",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "BUY"
    assert sig.strength == 0.9
    assert "strong" in sig.reason


def test_any_mode_buy_priority_over_sell() -> None:
    """When both BUY and SELL signals exist, BUY wins."""
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("BUY", 0.5),
            _StubStrategy("SELL", 0.9),  # stronger but ignored
        ],
        mode="any",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "BUY"


def test_any_mode_falls_back_to_sell() -> None:
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("SELL", 0.5, "s1"),
            _StubStrategy("SELL", 0.8, "s2"),
            _StubStrategy("HOLD"),
        ],
        mode="any",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "SELL"
    assert sig.strength == 0.8


def test_any_mode_all_hold_returns_hold() -> None:
    cs = CompositeStrategy(
        strategies=[_StubStrategy("HOLD"), _StubStrategy("HOLD")], mode="any"
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "HOLD"
    assert "All HOLD" in sig.reason


# ── majority mode ───────────────────────────────────────────────────────


def test_majority_mode_buy_wins_simple_majority() -> None:
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("BUY", 0.6),
            _StubStrategy("BUY", 0.7),
            _StubStrategy("SELL", 0.9),
        ],
        mode="majority",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "BUY"
    assert "MAJORITY 2/3" in sig.reason


def test_majority_mode_sell_wins_majority() -> None:
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("SELL", 0.5),
            _StubStrategy("SELL", 0.6),
            _StubStrategy("SELL", 0.7),
            _StubStrategy("BUY", 0.9),
        ],
        mode="majority",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "SELL"
    assert "MAJORITY 3/4" in sig.reason


def test_majority_mode_tie_returns_hold() -> None:
    """1 BUY + 1 SELL = no majority → HOLD."""
    cs = CompositeStrategy(
        strategies=[_StubStrategy("BUY"), _StubStrategy("SELL")], mode="majority"
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "HOLD"
    assert "No majority" in sig.reason


def test_majority_mode_half_not_a_majority() -> None:
    """2/4 is not > threshold (which is 2.0) → HOLD."""
    cs = CompositeStrategy(
        strategies=[
            _StubStrategy("BUY"),
            _StubStrategy("BUY"),
            _StubStrategy("SELL"),
            _StubStrategy("SELL"),
        ],
        mode="majority",
    )
    sig = cs.evaluate([1.0])
    assert sig.action == "HOLD"
