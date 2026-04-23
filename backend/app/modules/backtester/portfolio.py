from dataclasses import dataclass, field


@dataclass
class Trade:
    symbol: str
    action: str  # BUY or SELL
    date: str
    price: float
    shares: int
    cost: float  # including fees
    reason: str


@dataclass
class Portfolio:
    initial_capital: float
    cash: float = 0.0
    positions: dict[str, int] = field(default_factory=dict)  # symbol -> shares
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cash == 0.0:
            self.cash = self.initial_capital

    def buy(self, symbol: str, price: float, shares: int, date: str, fee_rate: float = 0.001425, reason: str = "") -> bool:
        cost = price * shares * (1 + fee_rate)
        if cost > self.cash:
            return False
        self.cash -= cost
        self.positions[symbol] = self.positions.get(symbol, 0) + shares
        self.trades.append(Trade(symbol=symbol, action="BUY", date=date, price=price, shares=shares, cost=cost, reason=reason))
        return True

    def sell(self, symbol: str, price: float, shares: int, date: str, fee_rate: float = 0.001425, tax_rate: float = 0.003, reason: str = "") -> bool:
        if self.positions.get(symbol, 0) < shares:
            return False
        proceeds = price * shares * (1 - fee_rate - tax_rate)
        self.cash += proceeds
        self.positions[symbol] -= shares
        if self.positions[symbol] == 0:
            del self.positions[symbol]
        self.trades.append(Trade(symbol=symbol, action="SELL", date=date, price=price, shares=shares, cost=proceeds, reason=reason))
        return True

    def total_value(self, current_prices: dict[str, float]) -> float:
        positions_value = sum(
            current_prices.get(symbol, 0) * shares
            for symbol, shares in self.positions.items()
        )
        return self.cash + positions_value

    def record_equity(self, current_prices: dict[str, float]) -> None:
        self.equity_curve.append(self.total_value(current_prices))
