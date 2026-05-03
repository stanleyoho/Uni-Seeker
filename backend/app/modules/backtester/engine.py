from dataclasses import dataclass, field

from app.models.price import StockPrice
from app.modules.backtester.metrics import BacktestMetrics, calculate_metrics
from app.modules.backtester.portfolio import Portfolio
from app.modules.strategy.base import Strategy

# -- Constants ----------------------------------------------------------------

MIN_DATA_POINTS = 20
DEFAULT_INITIAL_CAPITAL = 1_000_000
DEFAULT_FEE_RATE = 0.001425       # Taiwan stock broker fee (0.1425%)
DEFAULT_TAX_RATE = 0.003          # Taiwan stock transaction tax, sell side (0.3%)
DEFAULT_POSITION_SIZE = 0.1       # Fraction of cash per trade (10%)


@dataclass
class BacktestConfig:
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    fee_rate: float = DEFAULT_FEE_RATE       # 台股手續費 0.1425%
    tax_rate: float = DEFAULT_TAX_RATE       # 台股交易稅 0.3% (賣出)
    position_size: float = DEFAULT_POSITION_SIZE  # 每次投入資金比例 (10%)
    stop_loss: float | None = None    # percentage, e.g. 10.0 = sell if -10%
    take_profit: float | None = None  # percentage, e.g. 30.0 = sell if +30%


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
        chip_data: dict[str, list[dict]] | None = None,
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
        buy_price: float = 0.0

        # Build date-indexed chip data for O(1) lookup
        _chip_by_date: dict[str, dict[str, list[dict]]] = {}
        if chip_data:
            for key, records in chip_data.items():
                for rec in records:
                    d = rec.get("date", "")
                    _chip_by_date.setdefault(d, {}).setdefault(key, []).append(rec)

        for price in prices:
            close = float(price.close)
            closes_so_far.append(close)
            date_str = str(price.date)

            # Check stop-loss / take-profit before strategy evaluation
            forced_sell = False
            if symbol in portfolio.positions and buy_price > 0:
                pnl_pct = (close - buy_price) / buy_price * 100
                if (
                    self._config.stop_loss is not None
                    and pnl_pct <= -abs(self._config.stop_loss)
                ):
                    forced_sell = True
                    sell_reason = (
                        f"STOP_LOSS ({pnl_pct:.1f}% <= "
                        f"-{abs(self._config.stop_loss):.1f}%)"
                    )
                elif (
                    self._config.take_profit is not None
                    and pnl_pct >= abs(self._config.take_profit)
                ):
                    forced_sell = True
                    sell_reason = (
                        f"TAKE_PROFIT ({pnl_pct:.1f}% >= "
                        f"+{abs(self._config.take_profit):.1f}%)"
                    )

            if forced_sell:
                shares = portfolio.positions[symbol]
                portfolio.sell(
                    symbol, close, shares, date_str,
                    fee_rate=self._config.fee_rate,
                    tax_rate=self._config.tax_rate,
                    reason=sell_reason,
                )
                buy_price = 0.0
                portfolio.record_equity({symbol: close})
                continue

            # Build kwargs with chip data up to current date
            chip_kwargs: dict[str, object] = {}
            if chip_data:
                date_chip = _chip_by_date.get(date_str, {})
                chip_kwargs["institutional"] = date_chip.get("institutional", [])
                chip_kwargs["margin"] = date_chip.get("margin", [])
                chip_kwargs["shareholding"] = date_chip.get("shareholding", [])

            # Evaluate strategy
            signal = strategy.evaluate(closes_so_far, **chip_kwargs)

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
                    buy_price = close

            elif signal.action == "SELL" and symbol in portfolio.positions:
                shares = portfolio.positions[symbol]
                portfolio.sell(
                    symbol, close, shares, date_str,
                    fee_rate=self._config.fee_rate,
                    tax_rate=self._config.tax_rate,
                    reason=signal.reason,
                )
                buy_price = 0.0

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
