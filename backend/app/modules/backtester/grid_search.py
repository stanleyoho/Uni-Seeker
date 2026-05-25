"""Grid search engine for systematic strategy parameter optimization.

Generates all parameter combinations from a grid, builds composite strategies
via the registry, runs backtests, and ranks results by a weighted composite score
(40% return + 30% win rate + 30% Sharpe ratio).

All computation works on plain data (list[StockPrice]) with no DB access,
making it fully testable in isolation.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.models.price import StockPrice
from app.modules.backtester.engine import BacktestConfig, BacktestEngine
from app.modules.strategy.composite import CompositeStrategy
from app.modules.strategy.registry import StrategyRegistry
from app.obs.logging import get_logger

logger = get_logger(component="backtester")

# ---------------------------------------------------------------------------
# Param-to-strategy mapping
# ---------------------------------------------------------------------------

# Each entry maps a param-name prefix to (strategy_registry_key, constructor_kwarg).
_PARAM_MAP: dict[str, tuple[str, str]] = {
    "rsi_buy": ("rsi_oversold", "buy_threshold"),
    "rsi_sell": ("rsi_oversold", "sell_threshold"),
    "rsi_period": ("rsi_oversold", "period"),
    "bias_buy": ("bias_reversal", "buy_threshold"),
    "bias_sell": ("bias_reversal", "sell_threshold"),
    "bias_period": ("bias_reversal", "period"),
    "bb_std": ("bollinger_bounce", "num_std"),
    "bb_period": ("bollinger_bounce", "period"),
    "macd_fast": ("macd_crossover", "fast"),
    "macd_slow": ("macd_crossover", "slow"),
    "macd_signal": ("macd_crossover", "signal"),
    "ma_short": ("ma_crossover", "short_period"),
    "ma_long": ("ma_crossover", "long_period"),
}


def _build_strategy_params(
    strategy_keys: list[str],
    flat_params: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Convert flat grid params into per-strategy kwargs.

    Returns a dict keyed by strategy registry key, where each value is the
    kwargs dict to pass to ``registry.get(key, **kwargs)``.

    Only strategies listed in *strategy_keys* are included; unknown param
    prefixes are silently ignored so callers can mix strategy-specific and
    engine-level params (like ``mode``) in the same grid.
    """
    result: dict[str, dict[str, Any]] = {k: {} for k in strategy_keys}
    for param_name, value in flat_params.items():
        mapping = _PARAM_MAP.get(param_name)
        if mapping is None:
            continue
        strat_key, kwarg_name = mapping
        if strat_key in result:
            result[strat_key][kwarg_name] = value
    return result


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GridSearchConfig:
    """Configuration for a grid search run."""

    strategy_keys: list[str]
    param_grid: dict[str, list[Any]]
    composite_mode: str = "all"
    initial_capital: float = 1_000_000
    position_size: float = 0.95
    stop_loss: float | None = None
    take_profit: float | None = None
    min_trades: int = 6  # 最低交易次數（過濾極端低頻策略）
    min_win_rate: float = 50.0  # 最低勝率 (%)
    max_combinations: int = 10_000  # Safety limit to prevent DoS

    def total_combinations(self) -> int:
        """Return the number of parameter combinations in the grid."""
        if not self.param_grid:
            return 1
        count = 1
        for values in self.param_grid.values():
            count *= len(values)
        return count


@dataclass
class GridSearchResultItem:
    """Metrics for a single parameter combination."""

    name: str
    params: dict[str, Any]
    total_return: float
    annualized_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    sharpe: float
    wins: int
    losses: int


@dataclass
class GridSearchResult:
    """Aggregated result of a grid search run."""

    total_combos: int
    results: list[GridSearchResultItem]  # sorted by composite score descending
    best: GridSearchResultItem | None
    backtest_start: str
    backtest_end: str
    trading_days: int
    buy_hold_return: float


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

_WEIGHT_RETURN = 0.30
_WEIGHT_WIN_RATE = 0.25
_WEIGHT_SHARPE = 0.25
_WEIGHT_TRADE_FREQ = 0.20  # 鼓勵合理交易頻率
_IDEAL_TRADES = 20  # 理想交易次數（用於歸一化）


def compute_composite_scores(
    items: list[GridSearchResultItem],
    min_trades: int = 6,
    min_win_rate: float = 50.0,
) -> list[tuple[float, GridSearchResultItem]]:
    """Score and sort items by weighted composite.

    Weights: return 30% + win rate 25% + Sharpe 25% + trade frequency 20%.
    Items below min_trades or min_win_rate are excluded — these are
    statistically unreliable or impractical for real trading.

    Returns a list of (score, item) tuples sorted descending by score.
    """
    valid = [it for it in items if it.total_trades >= min_trades and it.win_rate >= min_win_rate]
    if not valid:
        return []

    max_ret = max((it.total_return for it in valid), default=1.0) or 1.0
    max_win = max((it.win_rate for it in valid), default=1.0) or 1.0
    max_sharpe = max((it.sharpe for it in valid), default=1.0) or 1.0

    scored: list[tuple[float, GridSearchResultItem]] = []
    for it in valid:
        trade_score = min(it.total_trades / _IDEAL_TRADES, 1.0)
        score = (
            (it.total_return / max_ret) * _WEIGHT_RETURN
            + (it.win_rate / max_win) * _WEIGHT_WIN_RATE
            + (it.sharpe / max_sharpe) * _WEIGHT_SHARPE
            + trade_score * _WEIGHT_TRADE_FREQ
        )
        scored.append((round(score, 6), it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Grid Search Engine
# ---------------------------------------------------------------------------


class GridSearchEngine:
    """Run exhaustive parameter grid search over composite strategies."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        config: GridSearchConfig,
        prices: list[StockPrice],
        symbol: str = "",
        progress_callback: Callable[[int], None] | None = None,
    ) -> GridSearchResult:
        """Execute grid search and return ranked results.

        Args:
            config: Grid search configuration (strategies, param grid, etc.).
            prices: Historical price data -- plain list, no DB needed.
            symbol: Stock symbol used for labeling.
            progress_callback: Optional callable receiving progress percentage
                (0-100) after each combination is evaluated.

        Returns:
            ``GridSearchResult`` with items sorted by composite score.
        """
        if not prices:
            return GridSearchResult(
                total_combos=0,
                results=[],
                best=None,
                backtest_start="",
                backtest_end="",
                trading_days=0,
                buy_hold_return=0.0,
            )

        if not symbol:
            # StockPrice ORM has no `symbol` attr; this dead-fallback
            # path is only triggered by old call sites that have since
            # been migrated. Keep but silence mypy.
            symbol = prices[0].symbol  # type: ignore[attr-defined]

        total = config.total_combinations()
        if total > config.max_combinations:
            raise ValueError(
                f"Grid search has {total:,} combinations, exceeding limit "
                f"of {config.max_combinations:,}. Reduce param_grid or "
                f"increase max_combinations."
            )

        combos = self._generate_combinations(config.param_grid)
        total = len(combos)
        items: list[GridSearchResultItem] = []
        skipped = 0

        for idx, flat_params in enumerate(combos):
            mode = flat_params.get("mode", config.composite_mode)
            item = self._evaluate_combination(
                config=config,
                flat_params=flat_params,
                mode=mode,
                prices=prices,
                symbol=symbol,
            )
            if item is not None:
                items.append(item)
            else:
                skipped += 1

            if progress_callback is not None:
                pct = int((idx + 1) / total * 100)
                progress_callback(pct)

        if skipped:
            logger.warning(
                "Grid search: %d of %d combinations skipped due to strategy construction errors.",
                skipped,
                total,
            )

        # Rank by composite score (filtered by min_trades + min_win_rate)
        scored = compute_composite_scores(
            items,
            min_trades=config.min_trades,
            min_win_rate=config.min_win_rate,
        )
        sorted_items = [it for _, it in scored]
        # Append filtered-out items at the end for reference
        filtered_ids = {id(it) for _, it in scored}
        remaining = [it for it in items if id(it) not in filtered_ids and it.total_trades > 0]
        remaining.sort(key=lambda x: x.total_return, reverse=True)
        sorted_items.extend(remaining)

        # Buy-and-hold return
        first_close = float(prices[0].close)
        last_close = float(prices[-1].close)
        buy_hold = (last_close / first_close - 1) * 100 if first_close > 0 else 0.0

        return GridSearchResult(
            total_combos=total,
            results=sorted_items,
            best=sorted_items[0] if sorted_items else None,
            backtest_start=str(prices[0].date),
            backtest_end=str(prices[-1].date),
            trading_days=len(prices),
            buy_hold_return=round(buy_hold, 2),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_combinations(
        param_grid: dict[str, list[Any]],
    ) -> list[dict[str, Any]]:
        """Cartesian product of all param values."""
        if not param_grid:
            return [{}]
        keys = list(param_grid.keys())
        values = [param_grid[k] for k in keys]
        return [dict(zip(keys, combo, strict=False)) for combo in itertools.product(*values)]

    def _evaluate_combination(
        self,
        config: GridSearchConfig,
        flat_params: dict[str, Any],
        mode: str,
        prices: list[StockPrice],
        symbol: str,
    ) -> GridSearchResultItem | None:
        """Build strategy from params, run backtest, return result item."""
        # Build per-strategy kwargs from the flat param dict
        strat_params = _build_strategy_params(config.strategy_keys, flat_params)

        # Instantiate each sub-strategy via the registry
        sub_strategies = []
        for key in config.strategy_keys:
            kwargs = strat_params.get(key, {})
            try:
                sub_strategies.append(self._registry.get(key, **kwargs))
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping strategy %s with params %s: %s", key, kwargs, exc)
                return None

        # Wrap in CompositeStrategy (or use single strategy directly)
        if len(sub_strategies) == 1:
            strategy = sub_strategies[0]
        else:
            strategy = CompositeStrategy(
                strategies=sub_strategies,
                mode=mode,
            )

        # Configure and run backtest
        bt_config = BacktestConfig(
            initial_capital=config.initial_capital,
            position_size=config.position_size,
            stop_loss=config.stop_loss,
            take_profit=config.take_profit,
        )
        engine = BacktestEngine(bt_config)
        result = engine.run(strategy, prices, symbol)
        metrics = result.metrics

        # Derive wins / losses from trade log
        wins, losses = self._count_wins_losses(result.trade_log)

        name = self._build_name(config.strategy_keys, flat_params, mode)

        return GridSearchResultItem(
            name=name,
            params=flat_params,
            total_return=metrics.total_return,
            annualized_return=metrics.annualized_return,
            max_drawdown=metrics.max_drawdown,
            win_rate=metrics.win_rate,
            total_trades=metrics.total_trades,
            profit_factor=metrics.profit_factor,
            sharpe=metrics.sharpe_ratio,
            wins=wins,
            losses=losses,
        )

    @staticmethod
    def _count_wins_losses(trade_log: list[dict[str, object]]) -> tuple[int, int]:
        """Count winning and losing round-trip trades from the log."""
        buys: list[float] = []
        wins = 0
        losses = 0
        for t in trade_log:
            if t.get("action") == "BUY":
                buys.append(float(t["price"]))  # type: ignore[arg-type]
            elif t.get("action") == "SELL" and buys:
                buy_price = buys.pop(0)
                if float(t["price"]) > buy_price:  # type: ignore[arg-type]
                    wins += 1
                else:
                    losses += 1
        return wins, losses

    @staticmethod
    def _build_name(
        strategy_keys: list[str],
        flat_params: dict[str, Any],
        mode: str,
    ) -> str:
        """Build a human-readable name from strategy keys and params."""
        key_labels = {
            "rsi_oversold": "RSI",
            "bias_reversal": "BIAS",
            "bollinger_bounce": "BB",
            "macd_crossover": "MACD",
            "ma_crossover": "MA",
            "rsi_bias_combo": "RSI+BIAS",
        }
        parts = [key_labels.get(k, k) for k in strategy_keys]
        strat_part = "+".join(parts)

        param_strs = []
        for k, v in sorted(flat_params.items()):
            if k == "mode":
                continue
            param_strs.append(f"{k}={v}")
        param_part = ",".join(param_strs) if param_strs else "default"

        return f"{strat_part}({param_part}) [{mode}]"
