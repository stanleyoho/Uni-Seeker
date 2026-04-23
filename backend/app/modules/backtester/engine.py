from dataclasses import dataclass, field

from app.models.price import StockPrice
from app.modules.backtester.metrics import BacktestMetrics, calculate_metrics
from app.modules.backtester.portfolio import Portfolio
from app.modules.strategy.base import Strategy


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000
    fee_rate: float = 0.001425  # 台股手續費 0.1425%
    tax_rate: float = 0.003     # 台股交易稅 0.3% (賣出)
    position_size: float = 0.1  # 每次投入資金比例 (10%)


@dataclass
class BacktestResult:
    config: BacktestConfig
    metrics: BacktestMetrics
    portfolio: Portfolio
    equity_curve: list[float] = field(default_factory=list)
    trade_log: list[dict[str, object]] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or BacktestConfig()

    def run(
        self,
        strategy: Strategy,
        prices: list[StockPrice],
        symbol: str = "",
    ) -> BacktestResult:
        if not prices:
            portfolio = Portfolio(initial_capital=self._config.initial_capital)
            return BacktestResult(
                config=self._config,
                metrics=calculate_metrics(portfolio),
                portfolio=portfolio,
            )

        if not symbol:
            symbol = prices[0].symbol

        portfolio = Portfolio(initial_capital=self._config.initial_capital)
        closes_so_far: list[float] = []

        for price in prices:
            close = float(price.close)
            closes_so_far.append(close)
            date_str = str(price.date)

            # Evaluate strategy
            signal = strategy.evaluate(closes_so_far)

            if signal.action == "BUY" and symbol not in portfolio.positions:
                # Calculate shares to buy
                invest_amount = portfolio.cash * self._config.position_size
                shares = int(invest_amount / close)
                if shares > 0:
                    portfolio.buy(
                        symbol, close, shares, date_str,
                        fee_rate=self._config.fee_rate,
                        reason=signal.reason,
                    )

            elif signal.action == "SELL" and symbol in portfolio.positions:
                shares = portfolio.positions[symbol]
                portfolio.sell(
                    symbol, close, shares, date_str,
                    fee_rate=self._config.fee_rate,
                    tax_rate=self._config.tax_rate,
                    reason=signal.reason,
                )

            portfolio.record_equity({symbol: close})

        return BacktestResult(
            config=self._config,
            metrics=calculate_metrics(portfolio),
            portfolio=portfolio,
            equity_curve=portfolio.equity_curve,
            trade_log=[
                {"action": t.action, "date": t.date, "price": t.price,
                 "shares": t.shares, "reason": t.reason}
                for t in portfolio.trades
            ],
        )
