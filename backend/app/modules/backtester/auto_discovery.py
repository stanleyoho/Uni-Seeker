"""Auto Discovery engine for automatic strategy optimization.

Runs in three phases:
  1. Single strategy scan – test all technical strategies with defaults, keep top N.
  2. Grid search – optimize parameters for the top strategies, keep top M.
  3. Composite test – combine best strategies in all/any/majority modes.

All computation works on plain data (list[StockPrice]) with no DB access,
making it fully testable in isolation.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from app.models.price import StockPrice
from app.modules.backtester.engine import BacktestConfig, BacktestEngine
from app.modules.backtester.grid_search import (
    GridSearchConfig,
    GridSearchEngine,
    compute_composite_scores,
)
from app.modules.strategy.composite import CompositeStrategy
from app.modules.strategy.registry import StrategyRegistry
from app.obs.logging import get_logger

logger = get_logger(component="backtester")

# ---------------------------------------------------------------------------
# Parameter grids per strategy (Phase 2)
# ---------------------------------------------------------------------------

_AUTO_GRIDS: dict[str, dict[str, list]] = {
    "rsi_oversold": {"rsi_buy": [20, 25, 30, 35], "rsi_sell": [65, 70, 75, 80]},
    "macd_crossover": {"macd_fast": [8, 12], "macd_slow": [21, 26], "macd_signal": [7, 9]},
    "bollinger_bounce": {"bb_period": [15, 20, 25], "bb_std": [1.5, 2.0, 2.5]},
    "bias_reversal": {"bias_period": [10, 20, 30], "bias_buy": [-3, -5, -7], "bias_sell": [3, 5, 7]},
    "ma_crossover": {"ma_short": [3, 5, 10], "ma_long": [15, 20, 30]},
    "rsi_bias_combo": {"rsi_buy": [25, 30, 35], "rsi_sell": [65, 70, 75], "bias_buy": [-3, -5], "bias_sell": [3, 5]},
}

# Map flat grid param names to (strategy_key, constructor_kwarg).
# Extends the grid_search _PARAM_MAP for rsi_bias_combo which accepts
# params directly rather than through sub-strategy delegation.
_DIRECT_PARAM_MAP: dict[str, dict[str, str]] = {
    "rsi_oversold": {"rsi_buy": "buy_threshold", "rsi_sell": "sell_threshold"},
    "macd_crossover": {"macd_fast": "fast", "macd_slow": "slow", "macd_signal": "signal"},
    "bollinger_bounce": {"bb_period": "period", "bb_std": "num_std"},
    "bias_reversal": {"bias_period": "period", "bias_buy": "buy_threshold", "bias_sell": "sell_threshold"},
    "ma_crossover": {"ma_short": "short_period", "ma_long": "long_period"},
    "rsi_bias_combo": {"rsi_buy": "rsi_buy", "rsi_sell": "rsi_sell", "bias_buy": "bias_buy", "bias_sell": "bias_sell"},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AutoDiscoveryConfig:
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    stop_loss: float | None = None
    take_profit: float | None = None
    top_n_phase1: int = 5  # keep top N from phase 1
    top_n_phase2: int = 3  # keep top N for composite phase


@dataclass
class AutoDiscoveryResultItem:
    phase: int  # 1, 2, or 3
    strategy_name: str
    strategy_keys: list[str]
    params: dict[str, Any]
    composite_mode: str | None  # None for single, "all"/"any"/"majority" for composite
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profit_factor: float


@dataclass
class AutoDiscoveryResult:
    symbol: str
    date_range_start: str
    date_range_end: str
    trading_days: int
    buy_hold_return: float
    total_strategies_tested: int
    phase1_results: list[AutoDiscoveryResultItem]
    phase2_results: list[AutoDiscoveryResultItem]
    phase3_results: list[AutoDiscoveryResultItem]
    best_overall: AutoDiscoveryResultItem | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_params_to_kwargs(strategy_key: str, flat_params: dict[str, Any]) -> dict[str, Any]:
    """Convert flat grid param names to constructor kwargs for a single strategy."""
    mapping = _DIRECT_PARAM_MAP.get(strategy_key, {})
    kwargs: dict[str, Any] = {}
    for flat_name, value in flat_params.items():
        ctor_name = mapping.get(flat_name)
        if ctor_name is not None:
            kwargs[ctor_name] = value
    return kwargs


def _compute_score(item: AutoDiscoveryResultItem) -> float:
    """Simple composite score for ranking across phases."""
    # Normalisation-free heuristic: weighted sum of key metrics
    return (
        item.total_return * 0.30
        + item.win_rate * 0.25
        + item.sharpe_ratio * 10.0 * 0.25  # scale sharpe up
        + min(item.total_trades / 20.0, 1.0) * 100.0 * 0.20
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AutoDiscoveryEngine:
    """Automatically discovers the best trading strategy for a stock."""

    _TECHNICAL_STRATEGIES = [
        "ma_crossover", "rsi_oversold", "macd_crossover",
        "bollinger_bounce", "bias_reversal", "rsi_bias_combo",
    ]

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def run(
        self,
        config: AutoDiscoveryConfig,
        prices: list[StockPrice],
        symbol: str = "",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> AutoDiscoveryResult:
        """Execute the full 3-phase auto discovery pipeline.

        Args:
            config: Discovery configuration.
            prices: Historical price data (plain list, no DB).
            symbol: Stock symbol for labeling.
            progress_callback: Optional ``(percent, message)`` reporter.

        Returns:
            ``AutoDiscoveryResult`` with ranked results from all phases.
        """
        if not prices:
            return AutoDiscoveryResult(
                symbol=symbol,
                date_range_start="",
                date_range_end="",
                trading_days=0,
                buy_hold_return=0.0,
                total_strategies_tested=0,
                phase1_results=[],
                phase2_results=[],
                phase3_results=[],
                best_overall=None,
            )

        if not symbol:
            symbol = getattr(prices[0], "symbol", "")

        def _progress(pct: int, msg: str) -> None:
            if progress_callback is not None:
                progress_callback(pct, msg)

        total_tested = 0

        # -- Phase 1 -------------------------------------------------------
        _progress(0, "Phase 1: scanning single strategies …")
        phase1, tested1 = self._phase1(config, prices, symbol, _progress)
        total_tested += tested1

        # -- Phase 2 -------------------------------------------------------
        top_keys = [r.strategy_keys[0] for r in phase1[: config.top_n_phase1]]
        _progress(30, f"Phase 2: grid search on top {len(top_keys)} strategies …")
        phase2, tested2 = self._phase2(config, prices, symbol, top_keys, _progress)
        total_tested += tested2

        # -- Phase 3 -------------------------------------------------------
        top_for_composite = phase2[: config.top_n_phase2]
        _progress(70, f"Phase 3: composite tests on top {len(top_for_composite)} strategies …")
        phase3, tested3 = self._phase3(config, prices, symbol, top_for_composite, _progress)
        total_tested += tested3

        # -- Buy & hold ----------------------------------------------------
        first_close = float(prices[0].close)
        last_close = float(prices[-1].close)
        buy_hold = (last_close / first_close - 1) * 100 if first_close > 0 else 0.0

        # -- Best overall --------------------------------------------------
        all_items = phase1 + phase2 + phase3
        best = max(all_items, key=_compute_score) if all_items else None

        _progress(100, "Discovery complete.")

        return AutoDiscoveryResult(
            symbol=symbol,
            date_range_start=str(prices[0].date),
            date_range_end=str(prices[-1].date),
            trading_days=len(prices),
            buy_hold_return=round(buy_hold, 2),
            total_strategies_tested=total_tested,
            phase1_results=phase1,
            phase2_results=phase2,
            phase3_results=phase3,
            best_overall=best,
        )

    # ------------------------------------------------------------------
    # Phase 1: single strategy scan
    # ------------------------------------------------------------------

    def _phase1(
        self,
        config: AutoDiscoveryConfig,
        prices: list[StockPrice],
        symbol: str,
        progress: Callable[[int, str], None],
    ) -> tuple[list[AutoDiscoveryResultItem], int]:
        """Test each technical strategy with default params."""
        results: list[AutoDiscoveryResultItem] = []
        strategies = self._TECHNICAL_STRATEGIES
        n = len(strategies)

        for i, key in enumerate(strategies):
            progress(int(i / n * 25), f"Phase 1: testing {key} …")
            try:
                strategy = self._registry.get(key)
            except (KeyError, TypeError) as exc:
                logger.warning("Phase 1: cannot build strategy %s: %s", key, exc)
                continue

            bt_config = BacktestConfig(
                initial_capital=config.initial_capital,
                position_size=config.position_size,
                stop_loss=config.stop_loss,
                take_profit=config.take_profit,
            )
            engine = BacktestEngine(bt_config)
            bt = engine.run(strategy, prices, symbol)
            m = bt.metrics

            results.append(AutoDiscoveryResultItem(
                phase=1,
                strategy_name=key,
                strategy_keys=[key],
                params={},
                composite_mode=None,
                total_return=m.total_return,
                annualized_return=m.annualized_return,
                max_drawdown=m.max_drawdown,
                sharpe_ratio=m.sharpe_ratio,
                win_rate=m.win_rate,
                total_trades=m.total_trades,
                profit_factor=m.profit_factor,
            ))

        # Sort by total_return descending
        results.sort(key=lambda r: r.total_return, reverse=True)
        return results, len(strategies)

    # ------------------------------------------------------------------
    # Phase 2: grid search
    # ------------------------------------------------------------------

    def _phase2(
        self,
        config: AutoDiscoveryConfig,
        prices: list[StockPrice],
        symbol: str,
        top_keys: list[str],
        progress: Callable[[int, str], None],
    ) -> tuple[list[AutoDiscoveryResultItem], int]:
        """Run focused grid search on top strategies from phase 1."""
        results: list[AutoDiscoveryResultItem] = []
        total_tested = 0

        for idx, key in enumerate(top_keys):
            grid = _AUTO_GRIDS.get(key)
            if grid is None:
                logger.info("Phase 2: no grid defined for %s, skipping.", key)
                continue

            progress(
                30 + int(idx / max(len(top_keys), 1) * 35),
                f"Phase 2: grid search on {key} …",
            )

            # Generate all param combinations
            param_names = list(grid.keys())
            param_values = [grid[k] for k in param_names]
            combos = [dict(zip(param_names, combo)) for combo in itertools.product(*param_values)]
            total_tested += len(combos)

            best_item: AutoDiscoveryResultItem | None = None
            best_score = float("-inf")

            for flat_params in combos:
                kwargs = _flat_params_to_kwargs(key, flat_params)
                try:
                    strategy = self._registry.get(key, **kwargs)
                except (KeyError, TypeError) as exc:
                    logger.warning("Phase 2: skip %s params %s: %s", key, kwargs, exc)
                    continue

                bt_config = BacktestConfig(
                    initial_capital=config.initial_capital,
                    position_size=config.position_size,
                    stop_loss=config.stop_loss,
                    take_profit=config.take_profit,
                )
                engine = BacktestEngine(bt_config)
                bt = engine.run(strategy, prices, symbol)
                m = bt.metrics

                item = AutoDiscoveryResultItem(
                    phase=2,
                    strategy_name=key,
                    strategy_keys=[key],
                    params=flat_params,
                    composite_mode=None,
                    total_return=m.total_return,
                    annualized_return=m.annualized_return,
                    max_drawdown=m.max_drawdown,
                    sharpe_ratio=m.sharpe_ratio,
                    win_rate=m.win_rate,
                    total_trades=m.total_trades,
                    profit_factor=m.profit_factor,
                )
                score = _compute_score(item)
                if score > best_score:
                    best_score = score
                    best_item = item

            if best_item is not None:
                results.append(best_item)

        # Sort by composite score descending
        results.sort(key=_compute_score, reverse=True)
        return results, total_tested

    # ------------------------------------------------------------------
    # Phase 3: composite strategy tests
    # ------------------------------------------------------------------

    def _phase3(
        self,
        config: AutoDiscoveryConfig,
        prices: list[StockPrice],
        symbol: str,
        top_items: list[AutoDiscoveryResultItem],
        progress: Callable[[int, str], None],
    ) -> tuple[list[AutoDiscoveryResultItem], int]:
        """Test composite combinations of the top strategies."""
        if len(top_items) < 2:
            return [], 0

        results: list[AutoDiscoveryResultItem] = []
        modes = ["all", "any", "majority"]
        total_tested = 0

        # Prepare strategy builders: (key, best_params) tuples
        strat_specs: list[tuple[str, dict[str, Any]]] = []
        for item in top_items:
            strat_specs.append((item.strategy_keys[0], item.params))

        # Generate 2-combos and 3-combos
        combos: list[list[int]] = []
        n = len(strat_specs)
        for r in (2, 3):
            if r <= n:
                combos.extend(list(c) for c in itertools.combinations(range(n), r))

        total_runs = len(combos) * len(modes)
        run_idx = 0

        for indices in combos:
            for mode in modes:
                run_idx += 1
                pct = 70 + int(run_idx / max(total_runs, 1) * 28)
                keys_in_combo = [strat_specs[i][0] for i in indices]
                progress(pct, f"Phase 3: {'+'.join(keys_in_combo)} [{mode}] …")

                sub_strategies = []
                all_params: dict[str, Any] = {}
                for i in indices:
                    key, flat_params = strat_specs[i]
                    kwargs = _flat_params_to_kwargs(key, flat_params)
                    try:
                        sub_strategies.append(self._registry.get(key, **kwargs))
                    except (KeyError, TypeError) as exc:
                        logger.warning("Phase 3: cannot build %s: %s", key, exc)
                        break
                    # Prefix params with strategy key for clarity
                    for k, v in flat_params.items():
                        all_params[f"{key}.{k}"] = v
                else:
                    # Only run if all sub-strategies were built successfully
                    composite = CompositeStrategy(strategies=sub_strategies, mode=mode)
                    bt_config = BacktestConfig(
                        initial_capital=config.initial_capital,
                        position_size=config.position_size,
                        stop_loss=config.stop_loss,
                        take_profit=config.take_profit,
                    )
                    engine = BacktestEngine(bt_config)
                    bt = engine.run(composite, prices, symbol)
                    m = bt.metrics

                    name = f"composite({'+'.join(keys_in_combo)}, {mode})"
                    results.append(AutoDiscoveryResultItem(
                        phase=3,
                        strategy_name=name,
                        strategy_keys=keys_in_combo,
                        params=all_params,
                        composite_mode=mode,
                        total_return=m.total_return,
                        annualized_return=m.annualized_return,
                        max_drawdown=m.max_drawdown,
                        sharpe_ratio=m.sharpe_ratio,
                        win_rate=m.win_rate,
                        total_trades=m.total_trades,
                        profit_factor=m.profit_factor,
                    ))
                    total_tested += 1

        total_tested += 0  # combos that failed don't count
        results.sort(key=_compute_score, reverse=True)
        return results, run_idx  # run_idx = total attempted
