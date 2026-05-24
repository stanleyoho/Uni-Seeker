"""Tests for PortfolioBacktestEngine — multi-stock portfolio backtester."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.modules.backtester.portfolio_backtest import (
    PortfolioAllocation,
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
    PortfolioBacktestResult,
    PortfolioTradeRecord,
    RebalanceConfig,
)
from app.modules.strategy.base import Signal, StrategyConfig

# ---------------------------------------------------------------------------
# Helpers: lightweight StockPrice mock + simple strategies
# ---------------------------------------------------------------------------


@dataclass
class MockStockPrice:
    """Minimal stand-in for StockPrice with the fields the engine reads."""

    date: date
    close: Decimal
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    volume: int = 10_000_000


def _make_prices(
    closes: list[float],
    start: date | None = None,
) -> list[MockStockPrice]:
    start = start or date(2026, 1, 2)
    return [
        MockStockPrice(
            date=start + timedelta(days=i),
            close=Decimal(str(c)),
            open=Decimal(str(c - 1)),
            high=Decimal(str(c + 2)),
            low=Decimal(str(c - 2)),
        )
        for i, c in enumerate(closes)
    ]


class AlwaysHoldStrategy:
    """Strategy that never signals BUY or SELL."""

    config = StrategyConfig(name="always_hold", description="hold forever")

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        return Signal(action="HOLD", symbol="", reason="always hold")


class BuyOnceStrategy:
    """Buys on the 2nd bar (index 1), then holds."""

    config = StrategyConfig(name="buy_once", description="buy on bar 2")

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) == 2:
            return Signal(action="BUY", symbol="", reason="buy signal")
        return Signal(action="HOLD", symbol="", reason="hold")


class BuyThenSellStrategy:
    """Buys on bar 2, sells on bar 5."""

    config = StrategyConfig(name="buy_sell", description="buy bar 2, sell bar 5")

    def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
        if len(closes) == 2:
            return Signal(action="BUY", symbol="", reason="buy signal")
        if len(closes) == 5:
            return Signal(action="SELL", symbol="", reason="sell signal")
        return Signal(action="HOLD", symbol="", reason="hold")


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_allocations_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        with pytest.raises(ValueError, match="At least one allocation"):
            engine.run([], {})

    def test_weights_not_summing_to_one_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.3, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.3, strategy=AlwaysHoldStrategy()),
        ]
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            engine.run(allocs, {"A": _make_prices([100]), "B": _make_prices([100])})

    def test_negative_weight_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        allocs = [
            PortfolioAllocation(symbol="A", weight=-0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=1.5, strategy=AlwaysHoldStrategy()),
        ]
        with pytest.raises(ValueError, match="must be in"):
            engine.run(allocs, {"A": _make_prices([100]), "B": _make_prices([100])})

    def test_duplicate_symbols_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        with pytest.raises(ValueError, match="Duplicate symbols"):
            engine.run(allocs, {"A": _make_prices([100])})

    def test_missing_price_data_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        with pytest.raises(ValueError, match="No price data"):
            engine.run(allocs, {"A": _make_prices([100])})

    def test_empty_price_data_raises(self) -> None:
        engine = PortfolioBacktestEngine()
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        with pytest.raises(ValueError, match="Empty price data"):
            engine.run(allocs, {"A": []})


# ---------------------------------------------------------------------------
# Basic run tests
# ---------------------------------------------------------------------------


class TestBasicRun:
    def test_single_stock_hold_returns_result(self) -> None:
        prices = _make_prices([100.0] * 20)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        assert isinstance(result, PortfolioBacktestResult)
        assert len(result.portfolio_equity_curve) == 20
        assert "A" in result.individual_equity_curves
        assert result.allocations[0]["symbol"] == "A"
        assert result.allocations[0]["weight"] == 1.0

    def test_two_stocks_equal_weight(self) -> None:
        prices_a = _make_prices([100.0] * 10)
        prices_b = _make_prices([200.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert len(result.portfolio_equity_curve) == 10
        assert "A" in result.individual_metrics
        assert "B" in result.individual_metrics

    def test_date_alignment_only_common_dates(self) -> None:
        """If stock A has 10 dates and stock B has 8, only the 8 common dates are used."""
        start = date(2026, 1, 2)
        prices_a = _make_prices([100.0] * 10, start=start)
        prices_b = _make_prices([200.0] * 8, start=start)  # 2 fewer days
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert len(result.portfolio_equity_curve) == 8

    def test_no_common_dates_returns_empty(self) -> None:
        prices_a = _make_prices([100.0] * 5, start=date(2026, 1, 1))
        prices_b = _make_prices([200.0] * 5, start=date(2026, 6, 1))
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert result.portfolio_equity_curve == []
        assert result.portfolio_metrics["total_return"] == 0.0


# ---------------------------------------------------------------------------
# Trade execution tests
# ---------------------------------------------------------------------------


class TestTradeExecution:
    def test_initial_allocation_buys_shares(self) -> None:
        """Initial allocation creates a BUY for the stock."""
        prices = _make_prices([100.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        initial_buys = [t for t in result.trade_log if t.reason == "initial_allocation"]
        assert len(initial_buys) == 1
        assert initial_buys[0].symbol == "A"
        assert initial_buys[0].shares > 0

    def test_sell_signal_sells_initial_position(self) -> None:
        """Strategy SELL signal works on position acquired via initial allocation."""
        prices = _make_prices([100.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=BuyThenSellStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        # BuyThenSellStrategy sells on bar 5; position was from initial allocation
        sell_trades = [t for t in result.trade_log if t.action == "SELL" and t.reason == "sell signal"]
        assert len(sell_trades) == 1

    def test_buy_after_sell_creates_trade(self) -> None:
        """After selling, a subsequent BUY signal re-enters the position."""

        class SellThenBuyStrategy:
            config = StrategyConfig(name="sell_buy", description="sell 3, buy 6")

            def evaluate(self, closes: list[float], **kwargs: object) -> Signal:
                if len(closes) == 3:
                    return Signal(action="SELL", symbol="", reason="sell signal")
                if len(closes) == 6:
                    return Signal(action="BUY", symbol="", reason="re-buy signal")
                return Signal(action="HOLD", symbol="", reason="hold")

        prices = _make_prices([100.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=SellThenBuyStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        buy_trades = [t for t in result.trade_log if t.action == "BUY" and t.reason == "re-buy signal"]
        assert len(buy_trades) == 1

    def test_force_close_at_end(self) -> None:
        """Positions still open at the end are force-closed."""
        prices = _make_prices([100.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        close_trades = [t for t in result.trade_log if t.reason == "force_close"]
        assert len(close_trades) == 1

    def test_initial_allocation_for_multiple_stocks(self) -> None:
        prices_a = _make_prices([100.0] * 5)
        prices_b = _make_prices([50.0] * 5)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.6, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.4, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        initial_buys = [t for t in result.trade_log if t.reason == "initial_allocation"]
        symbols_bought = {t.symbol for t in initial_buys}
        assert symbols_bought == {"A", "B"}


# ---------------------------------------------------------------------------
# Rebalancing tests
# ---------------------------------------------------------------------------


class TestRebalancing:
    def test_no_rebalance_by_default(self) -> None:
        prices_a = _make_prices([100.0 + i for i in range(50)])
        prices_b = _make_prices([100.0] * 50)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert result.rebalance_log == []

    def test_periodic_rebalance(self) -> None:
        # Stock A appreciates, B stays flat -> periodic rebalance should trigger
        prices_a = _make_prices([100.0 + i * 5 for i in range(40)])
        prices_b = _make_prices([100.0] * 40)
        config = PortfolioBacktestConfig(
            rebalance=RebalanceConfig(mode="periodic", period_days=10),
        )
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine(config)
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert len(result.rebalance_log) >= 1
        assert result.rebalance_log[0]["reason"] == "periodic"

    def test_threshold_rebalance(self) -> None:
        # Large divergence triggers threshold rebalance
        prices_a = _make_prices([100.0 + i * 10 for i in range(20)])
        prices_b = _make_prices([100.0] * 20)
        config = PortfolioBacktestConfig(
            rebalance=RebalanceConfig(mode="threshold", threshold_pct=3.0),
        )
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine(config)
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert len(result.rebalance_log) >= 1
        assert "threshold" in result.rebalance_log[0]["reason"]

    def test_rebalance_log_contains_adjustments(self) -> None:
        prices_a = _make_prices([100.0 + i * 10 for i in range(20)])
        prices_b = _make_prices([100.0] * 20)
        config = PortfolioBacktestConfig(
            rebalance=RebalanceConfig(mode="periodic", period_days=5),
        )
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine(config)
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        for entry in result.rebalance_log:
            assert "date" in entry
            assert "reason" in entry
            assert "adjustments" in entry

    def test_rebalance_trades_marked_correctly(self) -> None:
        prices_a = _make_prices([100.0 + i * 10 for i in range(20)])
        prices_b = _make_prices([100.0] * 20)
        config = PortfolioBacktestConfig(
            rebalance=RebalanceConfig(mode="periodic", period_days=5),
        )
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine(config)
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        rebalance_actions = {t.action for t in result.trade_log if t.reason == "rebalance"}
        # Should have both buys and sells during rebalancing
        assert rebalance_actions & {"REBALANCE_BUY", "REBALANCE_SELL"}


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_portfolio_metrics_keys_present(self) -> None:
        prices = _make_prices([100.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        expected_keys = {
            "total_return", "annualized_return", "max_drawdown",
            "sharpe_ratio", "win_rate", "total_trades",
            "avg_holding_days", "profit_factor",
        }
        assert expected_keys.issubset(result.portfolio_metrics.keys())

    def test_individual_metrics_per_symbol(self) -> None:
        prices_a = _make_prices([100.0 + i for i in range(20)])
        prices_b = _make_prices([50.0] * 20)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert "A" in result.individual_metrics
        assert "B" in result.individual_metrics
        assert "total_return" in result.individual_metrics["A"]
        assert "max_drawdown" in result.individual_metrics["A"]
        assert "sharpe_ratio" in result.individual_metrics["A"]
        assert "total_trades" in result.individual_metrics["A"]


# ---------------------------------------------------------------------------
# Equity curve tests
# ---------------------------------------------------------------------------


class TestEquityCurve:
    def test_portfolio_equity_length_matches_dates(self) -> None:
        prices = _make_prices([100.0] * 15)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        assert len(result.portfolio_equity_curve) == 15

    def test_individual_equity_length_matches_dates(self) -> None:
        prices_a = _make_prices([100.0] * 12)
        prices_b = _make_prices([200.0] * 12)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        assert len(result.individual_equity_curves["A"]) == 12
        assert len(result.individual_equity_curves["B"]) == 12

    def test_equity_positive_for_flat_prices(self) -> None:
        """With flat prices, portfolio value should stay near initial capital (minus fees)."""
        prices = _make_prices([100.0] * 10)
        config = PortfolioBacktestConfig(initial_capital=1_000_000)
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine(config)
        result = engine.run(allocs, {"A": prices})

        for val in result.portfolio_equity_curve:
            assert val > 0
        # With flat prices the value should be close to initial capital
        # (slightly less due to buy fees)
        assert result.portfolio_equity_curve[-1] > 990_000


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_custom_fees_affect_equity(self) -> None:
        """Higher fees reduce the final portfolio equity curve value."""
        prices = _make_prices([100.0 + i * 0.5 for i in range(20)])
        config_high = PortfolioBacktestConfig(
            initial_capital=500_000,
            fee_rate=0.05,
            tax_rate=0.05,
        )
        config_low = PortfolioBacktestConfig(
            initial_capital=500_000,
            fee_rate=0.0001,
            tax_rate=0.0001,
        )
        allocs_high = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        allocs_low = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        result_high = PortfolioBacktestEngine(config_high).run(allocs_high, {"A": prices})
        result_low = PortfolioBacktestEngine(config_low).run(allocs_low, {"A": prices})

        # With rising prices, low fees should leave more equity
        assert result_high.portfolio_equity_curve[-1] < result_low.portfolio_equity_curve[-1]

    def test_default_config(self) -> None:
        engine = PortfolioBacktestEngine()
        assert engine._config.initial_capital == 1_000_000
        assert engine._config.fee_rate == 0.001425
        assert engine._config.rebalance.mode == "none"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_day_data(self) -> None:
        prices = _make_prices([100.0])
        allocs = [
            PortfolioAllocation(symbol="A", weight=1.0, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices})

        assert len(result.portfolio_equity_curve) == 1

    def test_three_stocks_unequal_weights(self) -> None:
        prices_a = _make_prices([100.0] * 10)
        prices_b = _make_prices([200.0] * 10)
        prices_c = _make_prices([50.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="B", weight=0.3, strategy=AlwaysHoldStrategy()),
            PortfolioAllocation(symbol="C", weight=0.2, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(
            allocs,
            {"A": prices_a, "B": prices_b, "C": prices_c},
        )

        assert len(result.allocations) == 3
        assert "C" in result.individual_metrics

    def test_different_strategies_per_stock(self) -> None:
        """Each stock can have its own strategy; BuyThenSell on A triggers a mid-run sell."""
        prices_a = _make_prices([100.0] * 10)
        prices_b = _make_prices([200.0] * 10)
        allocs = [
            PortfolioAllocation(symbol="A", weight=0.5, strategy=BuyThenSellStrategy()),
            PortfolioAllocation(symbol="B", weight=0.5, strategy=AlwaysHoldStrategy()),
        ]
        engine = PortfolioBacktestEngine()
        result = engine.run(allocs, {"A": prices_a, "B": prices_b})

        # A should have a strategy-driven sell (bar 5)
        a_sells = [t for t in result.trade_log if t.symbol == "A" and t.reason == "sell signal"]
        assert len(a_sells) == 1

        # B should only have initial_allocation + force_close
        b_reasons = {t.reason for t in result.trade_log if t.symbol == "B"}
        assert b_reasons == {"initial_allocation", "force_close"}
