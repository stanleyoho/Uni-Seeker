from pydantic import BaseModel

from app.schemas.types import DecimalStr


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
    start_date: str | None = None  # YYYY-MM-DD, inclusive
    end_date: str | None = None  # YYYY-MM-DD, inclusive


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


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    metrics: MetricsResponse
    equity_curve: list[DecimalStr]
    trades: list[TradeRecord]


class AutoDiscoveryRequest(BaseModel):
    symbol: str
    initial_capital: float = 1_000_000
    position_size: float = 0.1
    stop_loss: float | None = None
    take_profit: float | None = None
    start_date: str | None = None  # YYYY-MM-DD, inclusive
    end_date: str | None = None  # YYYY-MM-DD, inclusive
