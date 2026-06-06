from pydantic import BaseModel

from app.schemas._base import StrictModel
from app.schemas.types import DecimalStr


class BacktestRequest(StrictModel):
    symbol: str
    strategy: str  # single strategy key, e.g. "ma_crossover"
    params: dict[str, object] = {}
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    stop_loss: float | None = None
    take_profit: float | None = None
    start_date: str | None = None  # YYYY-MM-DD, inclusive
    end_date: str | None = None  # YYYY-MM-DD, inclusive


class CompositeBacktestRequest(StrictModel):
    symbol: str
    strategies: list[str]  # e.g. ["rsi_oversold", "macd_crossover"]
    mode: str = "majority"  # "all", "any", "majority"
    strategy_params: dict[str, dict[str, object]] = {}  # per-strategy params
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    stop_loss: float | None = None
    take_profit: float | None = None
    start_date: str | None = None
    end_date: str | None = None


class TradeRecord(BaseModel):
    action: str
    date: str
    price: DecimalStr
    shares: int
    reason: str


class MetricsResponse(BaseModel):
    total_return: DecimalStr
    annualized_return: DecimalStr
    max_drawdown: DecimalStr
    sharpe_ratio: DecimalStr
    win_rate: DecimalStr
    total_trades: int
    profit_factor: DecimalStr


class MetricCIResponse(BaseModel):
    """Bootstrap confidence interval for a single metric.

    ``median`` is the central (50th-percentile) estimate; ``ci_low`` /
    ``ci_high`` are the 5th / 95th percentiles (a 90% CI). Decimal-as-string
    like every other metric field — the frontend coerces with ``Number()``.
    """

    median: DecimalStr
    ci_low: DecimalStr
    ci_high: DecimalStr


class BootstrapResponse(BaseModel):
    """Bootstrap confidence intervals for the backtest's key metrics.

    Produced by resampling the realised returns / trades with replacement
    ``samples`` times under a fixed ``seed`` (see
    ``app.modules.backtester.bootstrap``). A per-metric field is ``null``
    when its underlying sample was too small to bootstrap (e.g. a single
    trade, or fewer than two return observations).
    """

    samples: int
    seed: int
    annualized_return: MetricCIResponse | None = None
    sharpe_ratio: MetricCIResponse | None = None
    max_drawdown: MetricCIResponse | None = None
    win_rate: MetricCIResponse | None = None


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    metrics: MetricsResponse
    equity_curve: list[DecimalStr]
    trades: list[TradeRecord]
    # 90% bootstrap CIs (median + 5th/95th pct) on sharpe / CAGR /
    # max-drawdown / win-rate. ``null`` only if the backtest ran with
    # ``bootstrap_samples=0``.
    bootstrap: BootstrapResponse | None = None


class AutoDiscoveryRequest(StrictModel):
    symbol: str
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    stop_loss: float | None = None
    take_profit: float | None = None
    start_date: str | None = None  # YYYY-MM-DD, inclusive
    end_date: str | None = None  # YYYY-MM-DD, inclusive
