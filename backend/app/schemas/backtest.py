from pydantic import BaseModel


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str  # "ma_crossover" or "rsi_oversold"
    params: dict[str, object] = {}
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    fee_rate: float = 0.001425
    tax_rate: float = 0.003


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
