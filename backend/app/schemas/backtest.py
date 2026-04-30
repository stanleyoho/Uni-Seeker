from pydantic import BaseModel


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str  # single strategy key, e.g. "ma_crossover"
    params: dict[str, object] = {}
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    fee_rate: float = 0.001425
    tax_rate: float = 0.003
    stop_loss: float | None = None
    take_profit: float | None = None


class CompositeBacktestRequest(BaseModel):
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


class TradeRecord(BaseModel):
    action: str
    date: str
    price: float
    shares: int
    reason: str


class MetricsResponse(BaseModel):
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profit_factor: float


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    metrics: MetricsResponse
    equity_curve: list[float]
    trades: list[TradeRecord]
