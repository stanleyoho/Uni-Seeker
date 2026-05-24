"""Multi-stock portfolio backtester with rebalancing support.

Supports multiple stocks each with independent strategies, periodic or
threshold-based rebalancing, and produces both portfolio-level and
per-symbol metrics / equity curves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.models.price import StockPrice
from app.modules.backtester.metrics import calculate_metrics
from app.modules.backtester.portfolio import Portfolio
from app.modules.strategy.base import Strategy

_WEIGHT_TOLERANCE = 1e-4


@dataclass
class PortfolioAllocation:
    """Target allocation for a single stock within the portfolio."""

    symbol: str
    weight: float  # 0.0–1.0, must sum to 1.0 across all allocations
    strategy: Strategy


@dataclass
class RebalanceConfig:
    """Controls when the portfolio rebalances back to target weights."""

    mode: str = "none"  # "periodic", "threshold", "none"
    period_days: int = 30  # for periodic mode (trading days)
    threshold_pct: float = 5.0  # for threshold mode: rebalance if deviation exceeds this


@dataclass
class PortfolioBacktestConfig:
    """Top-level configuration for the portfolio backtest."""

    initial_capital: float = 1_000_000
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    rebalance: RebalanceConfig = field(default_factory=RebalanceConfig)


@dataclass
class PortfolioTradeRecord:
    """A single trade executed during the backtest."""

    date: str
    symbol: str
    action: str  # BUY, SELL, REBALANCE_BUY, REBALANCE_SELL
    price: float
    shares: int
    reason: str


@dataclass
class PortfolioBacktestResult:
    """Complete result of a portfolio backtest run."""

    portfolio_metrics: dict[str, Any]
    individual_metrics: dict[str, dict[str, Any]]
    portfolio_equity_curve: list[float]
    individual_equity_curves: dict[str, list[float]]
    trade_log: list[PortfolioTradeRecord]
    rebalance_log: list[dict[str, Any]]
    allocations: list[dict[str, Any]]


class PortfolioBacktestEngine:
    """Multi-stock portfolio backtester with rebalancing."""

    def __init__(self, config: PortfolioBacktestConfig | None = None) -> None:
        self._config = config or PortfolioBacktestConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        allocations: list[PortfolioAllocation],
        prices_map: dict[str, list[StockPrice]],
    ) -> PortfolioBacktestResult:
        """Execute the portfolio backtest.

        Parameters
        ----------
        allocations:
            Target allocations (symbol, weight, strategy) for each stock.
        prices_map:
            Mapping of symbol -> chronologically-sorted StockPrice list.

        Returns
        -------
        PortfolioBacktestResult with portfolio and per-symbol analytics.
        """
        self._validate_allocations(allocations)
        self._validate_prices(allocations, prices_map)

        symbols = [a.symbol for a in allocations]
        weight_map = {a.symbol: a.weight for a in allocations}
        strategy_map = {a.symbol: a.strategy for a in allocations}

        # Align dates: only keep dates present for ALL symbols
        aligned_dates = self._align_dates(symbols, prices_map)
        if not aligned_dates:
            return self._empty_result(allocations)

        # Build per-symbol price lookup: symbol -> {date_str -> close}
        price_lookup: dict[str, dict[str, float]] = {}
        for sym in symbols:
            price_lookup[sym] = {str(p.date): float(p.close) for p in prices_map[sym]}

        # State
        portfolio = Portfolio(initial_capital=self._config.initial_capital)
        closes_so_far: dict[str, list[float]] = {sym: [] for sym in symbols}
        individual_equity: dict[str, list[float]] = {sym: [] for sym in symbols}
        trade_log: list[PortfolioTradeRecord] = []
        rebalance_log: list[dict[str, Any]] = []
        days_since_rebalance = 0

        # ---- Initial allocation ----
        first_date = aligned_dates[0]
        first_prices = {sym: price_lookup[sym][first_date] for sym in symbols}
        self._initial_buy(
            portfolio,
            allocations,
            first_prices,
            first_date,
            trade_log,
        )

        # Record first-day equity
        portfolio.record_equity(first_prices)
        for sym in symbols:
            closes_so_far[sym].append(first_prices[sym])
            individual_equity[sym].append(first_prices[sym] * portfolio.positions.get(sym, 0))

        # ---- Daily loop (skip first date — already processed) ----
        for date_str in aligned_dates[1:]:
            current_prices = {sym: price_lookup[sym][date_str] for sym in symbols}

            # Accumulate closes for strategy evaluation
            for sym in symbols:
                closes_so_far[sym].append(current_prices[sym])

            # Evaluate each stock's strategy and execute signals
            for alloc in allocations:
                sym = alloc.symbol
                signal = strategy_map[sym].evaluate(closes_so_far[sym])

                if signal.action == "BUY" and sym not in portfolio.positions:
                    invest = portfolio.cash * weight_map[sym]
                    shares = int(invest / (current_prices[sym] * (1 + self._config.fee_rate)))
                    if shares > 0:
                        ok = portfolio.buy(
                            sym,
                            current_prices[sym],
                            shares,
                            date_str,
                            fee_rate=self._config.fee_rate,
                            reason=signal.reason,
                        )
                        if ok:
                            trade_log.append(
                                PortfolioTradeRecord(
                                    date=date_str,
                                    symbol=sym,
                                    action="BUY",
                                    price=current_prices[sym],
                                    shares=shares,
                                    reason=signal.reason,
                                )
                            )

                elif signal.action == "SELL" and sym in portfolio.positions:
                    shares = portfolio.positions[sym]
                    ok = portfolio.sell(
                        sym,
                        current_prices[sym],
                        shares,
                        date_str,
                        fee_rate=self._config.fee_rate,
                        tax_rate=self._config.tax_rate,
                        reason=signal.reason,
                    )
                    if ok:
                        trade_log.append(
                            PortfolioTradeRecord(
                                date=date_str,
                                symbol=sym,
                                action="SELL",
                                price=current_prices[sym],
                                shares=shares,
                                reason=signal.reason,
                            )
                        )

            # Check rebalancing
            days_since_rebalance += 1
            should_rebalance, reason = self._should_rebalance(
                portfolio,
                current_prices,
                weight_map,
                days_since_rebalance,
            )
            if should_rebalance:
                adjustments = self._rebalance(
                    portfolio,
                    current_prices,
                    weight_map,
                    date_str,
                    trade_log,
                )
                if adjustments:
                    rebalance_log.append(
                        {"date": date_str, "reason": reason, "adjustments": adjustments}
                    )
                days_since_rebalance = 0

            # Record equity
            portfolio.record_equity(current_prices)
            for sym in symbols:
                individual_equity[sym].append(current_prices[sym] * portfolio.positions.get(sym, 0))

        # ---- Force close all positions ----
        last_date = aligned_dates[-1]
        last_prices = {sym: price_lookup[sym][last_date] for sym in symbols}
        self._force_close(portfolio, last_prices, last_date, trade_log)

        # ---- Calculate metrics ----
        portfolio_metrics = self._compute_portfolio_metrics(portfolio)
        individual_metrics = self._compute_individual_metrics(
            symbols,
            individual_equity,
            trade_log,
        )

        return PortfolioBacktestResult(
            portfolio_metrics=portfolio_metrics,
            individual_metrics=individual_metrics,
            portfolio_equity_curve=portfolio.equity_curve,
            individual_equity_curves=individual_equity,
            trade_log=trade_log,
            rebalance_log=rebalance_log,
            allocations=[
                {"symbol": a.symbol, "weight": a.weight, "strategy": a.strategy.config.name}
                for a in allocations
            ],
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_allocations(allocations: list[PortfolioAllocation]) -> None:
        if not allocations:
            raise ValueError("At least one allocation is required.")

        total_weight = sum(a.weight for a in allocations)
        if abs(total_weight - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(f"Allocation weights must sum to 1.0 (got {total_weight:.6f}).")

        for alloc in allocations:
            if alloc.weight <= 0 or alloc.weight > 1.0:
                raise ValueError(
                    f"Weight for {alloc.symbol} must be in (0, 1.0], got {alloc.weight}."
                )

        symbols = [a.symbol for a in allocations]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate symbols in allocations.")

    @staticmethod
    def _validate_prices(
        allocations: list[PortfolioAllocation],
        prices_map: dict[str, list[StockPrice]],
    ) -> None:
        for alloc in allocations:
            if alloc.symbol not in prices_map:
                raise ValueError(f"No price data provided for symbol '{alloc.symbol}'.")
            if not prices_map[alloc.symbol]:
                raise ValueError(f"Empty price data for symbol '{alloc.symbol}'.")

    # ------------------------------------------------------------------
    # Date alignment
    # ------------------------------------------------------------------

    @staticmethod
    def _align_dates(
        symbols: list[str],
        prices_map: dict[str, list[StockPrice]],
    ) -> list[str]:
        """Return sorted list of date strings present in ALL symbols' data."""
        date_sets = [{str(p.date) for p in prices_map[sym]} for sym in symbols]
        common = date_sets[0]
        for ds in date_sets[1:]:
            common &= ds
        return sorted(common)

    # ------------------------------------------------------------------
    # Initial buy
    # ------------------------------------------------------------------

    def _initial_buy(
        self,
        portfolio: Portfolio,
        allocations: list[PortfolioAllocation],
        prices: dict[str, float],
        date_str: str,
        trade_log: list[PortfolioTradeRecord],
    ) -> None:
        """Distribute initial capital according to target weights.

        Pre-computes each stock's budget from the initial capital to avoid
        rounding/fee issues when buying sequentially.
        """
        total_capital = portfolio.cash
        for alloc in allocations:
            budget = total_capital * alloc.weight
            price = prices[alloc.symbol]
            # Account for fees so the buy will not be rejected
            shares = int(budget / (price * (1 + self._config.fee_rate)))
            if shares > 0:
                ok = portfolio.buy(
                    alloc.symbol,
                    price,
                    shares,
                    date_str,
                    fee_rate=self._config.fee_rate,
                    reason="initial_allocation",
                )
                if ok:
                    trade_log.append(
                        PortfolioTradeRecord(
                            date=date_str,
                            symbol=alloc.symbol,
                            action="BUY",
                            price=price,
                            shares=shares,
                            reason="initial_allocation",
                        )
                    )

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def _should_rebalance(
        self,
        portfolio: Portfolio,
        current_prices: dict[str, float],
        weight_map: dict[str, float],
        days_since: int,
    ) -> tuple[bool, str]:
        """Determine whether a rebalance should be triggered."""
        mode = self._config.rebalance.mode

        if mode == "none":
            return False, ""

        if mode == "periodic":
            if days_since >= self._config.rebalance.period_days:
                return True, "periodic"
            return False, ""

        if mode == "threshold":
            total_value = portfolio.total_value(current_prices)
            if total_value <= 0:
                return False, ""
            for sym, target_w in weight_map.items():
                position_value = current_prices.get(sym, 0) * portfolio.positions.get(sym, 0)
                actual_w = position_value / total_value
                deviation = abs(actual_w - target_w) * 100  # as percentage points
                if deviation > self._config.rebalance.threshold_pct:
                    return True, f"threshold ({sym}: {actual_w:.2%} vs target {target_w:.2%})"
            return False, ""

        return False, ""

    def _rebalance(
        self,
        portfolio: Portfolio,
        current_prices: dict[str, float],
        weight_map: dict[str, float],
        date_str: str,
        trade_log: list[PortfolioTradeRecord],
    ) -> dict[str, Any]:
        """Execute rebalance trades to bring positions back to target weights.

        Strategy: first sell overweight positions (freeing cash), then buy
        underweight positions.

        Returns a dict of adjustments: {symbol: shares_delta, ...}
        """
        total_value = portfolio.total_value(current_prices)
        if total_value <= 0:
            return {}

        # Compute target shares for each symbol
        target_shares: dict[str, int] = {}
        for sym, target_w in weight_map.items():
            target_value = total_value * target_w
            target_shares[sym] = int(target_value / current_prices[sym])

        current_shares: dict[str, int] = {
            sym: portfolio.positions.get(sym, 0) for sym in weight_map
        }

        adjustments: dict[str, int] = {}

        # Phase 1: sell overweight positions
        for sym in weight_map:
            delta = target_shares[sym] - current_shares[sym]
            if delta < 0:
                sell_qty = abs(delta)
                if sell_qty > 0 and portfolio.positions.get(sym, 0) >= sell_qty:
                    ok = portfolio.sell(
                        sym,
                        current_prices[sym],
                        sell_qty,
                        date_str,
                        fee_rate=self._config.fee_rate,
                        tax_rate=self._config.tax_rate,
                        reason="rebalance",
                    )
                    if ok:
                        adjustments[sym] = -sell_qty
                        trade_log.append(
                            PortfolioTradeRecord(
                                date=date_str,
                                symbol=sym,
                                action="REBALANCE_SELL",
                                price=current_prices[sym],
                                shares=sell_qty,
                                reason="rebalance",
                            )
                        )

        # Phase 2: buy underweight positions
        for sym in weight_map:
            delta = target_shares[sym] - current_shares.get(sym, 0) - adjustments.get(sym, 0)
            # Recalculate since sells freed cash
            actual_held = portfolio.positions.get(sym, 0)
            buy_qty = target_shares[sym] - actual_held
            if buy_qty > 0:
                cost = current_prices[sym] * buy_qty * (1 + self._config.fee_rate)
                if cost <= portfolio.cash:
                    ok = portfolio.buy(
                        sym,
                        current_prices[sym],
                        buy_qty,
                        date_str,
                        fee_rate=self._config.fee_rate,
                        reason="rebalance",
                    )
                    if ok:
                        adjustments[sym] = adjustments.get(sym, 0) + buy_qty
                        trade_log.append(
                            PortfolioTradeRecord(
                                date=date_str,
                                symbol=sym,
                                action="REBALANCE_BUY",
                                price=current_prices[sym],
                                shares=buy_qty,
                                reason="rebalance",
                            )
                        )

        return adjustments

    # ------------------------------------------------------------------
    # Force close
    # ------------------------------------------------------------------

    def _force_close(
        self,
        portfolio: Portfolio,
        prices: dict[str, float],
        date_str: str,
        trade_log: list[PortfolioTradeRecord],
    ) -> None:
        """Sell all remaining positions at the final date's prices."""
        for sym in list(portfolio.positions.keys()):
            shares = portfolio.positions[sym]
            if shares > 0:
                ok = portfolio.sell(
                    sym,
                    prices[sym],
                    shares,
                    date_str,
                    fee_rate=self._config.fee_rate,
                    tax_rate=self._config.tax_rate,
                    reason="force_close",
                )
                if ok:
                    trade_log.append(
                        PortfolioTradeRecord(
                            date=date_str,
                            symbol=sym,
                            action="SELL",
                            price=prices[sym],
                            shares=shares,
                            reason="force_close",
                        )
                    )

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_portfolio_metrics(self, portfolio: Portfolio) -> dict[str, Any]:
        """Use existing calculate_metrics on the full portfolio."""
        metrics = calculate_metrics(portfolio)
        return {
            "total_return": metrics.total_return,
            "annualized_return": metrics.annualized_return,
            "max_drawdown": metrics.max_drawdown,
            "sharpe_ratio": metrics.sharpe_ratio,
            "win_rate": metrics.win_rate,
            "total_trades": metrics.total_trades,
            "avg_holding_days": metrics.avg_holding_days,
            "profit_factor": metrics.profit_factor,
        }

    @staticmethod
    def _compute_individual_metrics(
        symbols: list[str],
        individual_equity: dict[str, list[float]],
        trade_log: list[PortfolioTradeRecord],
    ) -> dict[str, dict[str, Any]]:
        """Compute per-symbol metrics from individual equity curves."""
        result: dict[str, dict[str, Any]] = {}

        for sym in symbols:
            curve = individual_equity[sym]
            if len(curve) < 2 or curve[0] == 0:
                result[sym] = {
                    "total_return": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                    "total_trades": 0,
                }
                continue

            # Total return
            # Find the first non-zero value as reference
            first_val = next((v for v in curve if v > 0), 0.0)
            if first_val == 0:
                result[sym] = {
                    "total_return": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                    "total_trades": 0,
                }
                continue

            total_return = (curve[-1] / first_val - 1) * 100

            # Max drawdown
            peak = curve[0]
            max_dd = 0.0
            for val in curve:
                if val > peak:
                    peak = val
                if peak > 0:
                    dd = (val - peak) / peak * 100
                    if dd < max_dd:
                        max_dd = dd

            # Sharpe from daily returns (skip zero-value days)
            daily_returns: list[float] = []
            for i in range(1, len(curve)):
                if curve[i - 1] > 0 and curve[i] > 0:
                    daily_returns.append(curve[i] / curve[i - 1] - 1)
            if daily_returns:
                avg_r = sum(daily_returns) / len(daily_returns)
                std_r = math.sqrt(sum((r - avg_r) ** 2 for r in daily_returns) / len(daily_returns))
                sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
            else:
                sharpe = 0.0

            sym_trades = [t for t in trade_log if t.symbol == sym]

            result[sym] = {
                "total_return": round(total_return, 2),
                "max_drawdown": round(max_dd, 2),
                "sharpe_ratio": round(sharpe, 4),
                "total_trades": len(sym_trades),
            }

        return result

    # ------------------------------------------------------------------
    # Empty result helper
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(allocations: list[PortfolioAllocation]) -> PortfolioBacktestResult:
        return PortfolioBacktestResult(
            portfolio_metrics={
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "avg_holding_days": 0.0,
                "profit_factor": 0.0,
            },
            individual_metrics={},
            portfolio_equity_curve=[],
            individual_equity_curves={},
            trade_log=[],
            rebalance_log=[],
            allocations=[
                {"symbol": a.symbol, "weight": a.weight, "strategy": a.strategy.config.name}
                for a in allocations
            ],
        )
