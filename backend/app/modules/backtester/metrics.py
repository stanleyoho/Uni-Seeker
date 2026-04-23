import math
from dataclasses import dataclass

from app.modules.backtester.portfolio import Portfolio


@dataclass
class BacktestMetrics:
    total_return: float  # percentage
    annualized_return: float
    max_drawdown: float  # percentage (negative)
    sharpe_ratio: float
    win_rate: float  # percentage
    total_trades: int
    avg_holding_days: float
    profit_factor: float


def calculate_metrics(portfolio: Portfolio, trading_days: int = 252) -> BacktestMetrics:
    equity = portfolio.equity_curve
    if len(equity) < 2:
        return BacktestMetrics(
            total_return=0, annualized_return=0, max_drawdown=0,
            sharpe_ratio=0, win_rate=0, total_trades=0,
            avg_holding_days=0, profit_factor=0,
        )

    # Total return
    total_return = (equity[-1] / equity[0] - 1) * 100

    # Annualized return
    n_days = len(equity)
    years = n_days / trading_days
    if years > 0 and equity[0] > 0:
        annualized = ((equity[-1] / equity[0]) ** (1 / years) - 1) * 100
    else:
        annualized = 0.0

    # Max drawdown
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # Daily returns for Sharpe
    daily_returns = [(equity[i] / equity[i - 1] - 1) for i in range(1, len(equity)) if equity[i - 1] > 0]
    if daily_returns:
        avg_return = sum(daily_returns) / len(daily_returns)
        std_return = math.sqrt(sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns))
        sharpe = (avg_return / std_return * math.sqrt(trading_days)) if std_return > 0 else 0.0
    else:
        sharpe = 0.0

    # Win rate and profit factor
    trades = portfolio.trades
    sell_trades = [t for t in trades if t.action == "SELL"]
    buy_map: dict[str, list[float]] = {}
    wins = 0
    total_profit = 0.0
    total_loss = 0.0

    for t in trades:
        if t.action == "BUY":
            buy_map.setdefault(t.symbol, []).append(t.price)
        elif t.action == "SELL" and t.symbol in buy_map and buy_map[t.symbol]:
            buy_price = buy_map[t.symbol].pop(0)
            pnl = (t.price - buy_price) * t.shares
            if pnl > 0:
                wins += 1
                total_profit += pnl
            else:
                total_loss += abs(pnl)

    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0.0
    profit_factor = (total_profit / total_loss) if total_loss > 0 else float("inf") if total_profit > 0 else 0.0

    return BacktestMetrics(
        total_return=round(total_return, 2),
        annualized_return=round(annualized, 2),
        max_drawdown=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 4),
        win_rate=round(win_rate, 2),
        total_trades=len(trades),
        avg_holding_days=0,  # simplified
        profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
    )
