"""
00631L (元大台灣50正2) 複合策略回測
策略：布林通道 + 乖離率 + RSI 組合，低買高賣

測試不同參數組合 + 不同投票模式，找出最佳獲利配置
"""

import itertools
import math
import sys
from dataclasses import dataclass, field

import yfinance as yf

# ── Data ──────────────────────────────────────────────────────────

print("Downloading 00631L.TW data...")
df = yf.download("00631L.TW", start="2020-01-01", auto_adjust=True)
close_series = df["Close"].squeeze().dropna()
closes = [float(c) for c in close_series.values]
dates = [str(d.date()) for d in close_series.index]
print(f"Loaded {len(closes)} trading days: {dates[0]} ~ {dates[-1]}")
print(f"Price range: {min(closes):.2f} ~ {max(closes):.2f}")
print()

# ── Strategies ────────────────────────────────────────────────────

def calc_rsi(data: list[float], period: int) -> float | None:
    if len(data) <= period:
        return None
    changes = [data[i] - data[i - 1] for i in range(1, len(data))]
    gains = [max(c, 0) for c in changes[-period:]]
    losses = [abs(min(c, 0)) for c in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def calc_bias(data: list[float], period: int) -> float | None:
    if len(data) < period:
        return None
    ma = sum(data[-period:]) / period
    return (data[-1] - ma) / ma * 100


def calc_bollinger(data: list[float], period: int, num_std: float) -> tuple[float, float, float] | None:
    if len(data) < period:
        return None
    window = data[-period:]
    sma = sum(window) / period
    variance = sum((x - sma) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return sma - num_std * std, sma, sma + num_std * std  # lower, middle, upper


# ── Backtest Engine ───────────────────────────────────────────────

@dataclass
class Trade:
    date: str
    action: str
    price: float
    shares: int
    reason: str


@dataclass
class BacktestResult:
    name: str
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    profit_factor: float
    sharpe: float
    buy_hold_return_pct: float  # benchmark
    trades: list[Trade] = field(default_factory=list)


def run_backtest(
    name: str,
    closes: list[float],
    dates: list[str],
    signal_fn,  # (closes_so_far) -> "BUY" | "SELL" | "HOLD", reason
    initial_capital: float = 1_000_000,
    position_size: float = 0.95,
    fee_rate: float = 0.001425,
    tax_rate: float = 0.003,
) -> BacktestResult:
    cash = initial_capital
    shares = 0
    trades: list[Trade] = []
    equity_curve: list[float] = []
    buy_price = 0.0

    for i in range(1, len(closes)):
        price = closes[i]
        closes_so_far = closes[: i + 1]
        action, reason = signal_fn(closes_so_far)

        if action == "BUY" and shares == 0:
            invest = cash * position_size
            buy_shares = int(invest / (price * (1 + fee_rate)))
            if buy_shares > 0:
                cost = buy_shares * price * (1 + fee_rate)
                cash -= cost
                shares = buy_shares
                buy_price = price
                trades.append(Trade(dates[i], "BUY", price, buy_shares, reason))

        elif action == "SELL" and shares > 0:
            proceeds = shares * price * (1 - fee_rate - tax_rate)
            cash += proceeds
            trades.append(Trade(dates[i], "SELL", price, shares, reason))
            shares = 0

        equity = cash + shares * price
        equity_curve.append(equity)

    # Force close if still holding
    if shares > 0:
        final_price = closes[-1]
        proceeds = shares * final_price * (1 - fee_rate - tax_rate)
        cash += proceeds
        equity_curve[-1] = cash

    final_equity = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_equity / initial_capital - 1) * 100
    n_days = len(equity_curve)
    years = n_days / 252
    ann_return = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    # Max drawdown
    peak = equity_curve[0] if equity_curve else initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # Win rate
    sell_trades = [t for t in trades if t.action == "SELL"]
    buy_trades = [t for t in trades if t.action == "BUY"]
    wins = 0
    total_profit = 0.0
    total_loss = 0.0
    for j, st in enumerate(sell_trades):
        if j < len(buy_trades):
            pnl = (st.price - buy_trades[j].price) * st.shares
            if pnl > 0:
                wins += 1
                total_profit += pnl
            else:
                total_loss += abs(pnl)
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

    profit_factor = (total_profit / total_loss) if total_loss > 0 else (999 if total_profit > 0 else 0)

    # Sharpe
    if len(equity_curve) > 1:
        daily_returns = [(equity_curve[i] / equity_curve[i - 1] - 1) for i in range(1, len(equity_curve))]
        avg_r = sum(daily_returns) / len(daily_returns)
        std_r = math.sqrt(sum((r - avg_r) ** 2 for r in daily_returns) / len(daily_returns))
        sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0
    else:
        sharpe = 0

    buy_hold = (closes[-1] / closes[0] - 1) * 100

    return BacktestResult(
        name=name,
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(ann_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 2),
        total_trades=len(trades),
        profit_factor=round(min(profit_factor, 999), 2),
        sharpe=round(sharpe, 4),
        buy_hold_return_pct=round(buy_hold, 2),
        trades=trades,
    )


# ── Signal Functions ──────────────────────────────────────────────

def make_composite_signal(
    rsi_period=14, rsi_buy=30, rsi_sell=70,
    bias_period=20, bias_buy=-5, bias_sell=5,
    bb_period=20, bb_std=2.0,
    mode="majority",
):
    def signal_fn(closes_so_far):
        signals = []  # list of "BUY" / "SELL" / "HOLD"
        reasons = []

        # RSI
        rsi = calc_rsi(closes_so_far, rsi_period)
        if rsi is not None:
            if rsi < rsi_buy:
                signals.append("BUY")
                reasons.append(f"RSI={rsi:.1f}<{rsi_buy}")
            elif rsi > rsi_sell:
                signals.append("SELL")
                reasons.append(f"RSI={rsi:.1f}>{rsi_sell}")
            else:
                signals.append("HOLD")
        else:
            signals.append("HOLD")

        # BIAS
        bias = calc_bias(closes_so_far, bias_period)
        if bias is not None:
            if bias <= bias_buy:
                signals.append("BUY")
                reasons.append(f"BIAS={bias:.2f}%<={bias_buy}%")
            elif bias >= bias_sell:
                signals.append("SELL")
                reasons.append(f"BIAS={bias:.2f}%>={bias_sell}%")
            else:
                signals.append("HOLD")
        else:
            signals.append("HOLD")

        # Bollinger
        bb = calc_bollinger(closes_so_far, bb_period, bb_std)
        if bb is not None:
            lower, middle, upper = bb
            price = closes_so_far[-1]
            if price <= lower:
                signals.append("BUY")
                reasons.append(f"Price<BB_lower({lower:.2f})")
            elif price >= upper:
                signals.append("SELL")
                reasons.append(f"Price>BB_upper({upper:.2f})")
            else:
                signals.append("HOLD")
        else:
            signals.append("HOLD")

        buys = signals.count("BUY")
        sells = signals.count("SELL")
        total = len(signals)
        reason_str = " | ".join(reasons) if reasons else "No signal"

        if mode == "all":
            if buys == total:
                return "BUY", f"[ALL] {reason_str}"
            if sells == total:
                return "SELL", f"[ALL] {reason_str}"
        elif mode == "any":
            if buys > 0:
                return "BUY", f"[ANY] {reason_str}"
            if sells > 0:
                return "SELL", f"[ANY] {reason_str}"
        else:  # majority
            if buys > total / 2:
                return "BUY", f"[MAJ {buys}/{total}] {reason_str}"
            if sells > total / 2:
                return "SELL", f"[MAJ {sells}/{total}] {reason_str}"

        return "HOLD", "No consensus"

    return signal_fn


# ── Parameter Grid Search ─────────────────────────────────────────

param_grid = {
    "rsi_period": [14],
    "rsi_buy": [25, 30, 35],
    "rsi_sell": [65, 70, 75],
    "bias_period": [10, 20],
    "bias_buy": [-3, -5, -7],
    "bias_sell": [3, 5, 7],
    "bb_period": [20],
    "bb_std": [1.5, 2.0, 2.5],
    "mode": ["all", "majority", "any"],
}

keys = list(param_grid.keys())
values = list(param_grid.values())
combos = list(itertools.product(*values))
print(f"Testing {len(combos)} parameter combinations...")
print("=" * 120)

results: list[BacktestResult] = []

for combo in combos:
    params = dict(zip(keys, combo))
    signal_fn = make_composite_signal(**params)
    name = (
        f"RSI({params['rsi_period']},{params['rsi_buy']},{params['rsi_sell']}) "
        f"BIAS({params['bias_period']},{params['bias_buy']},{params['bias_sell']}) "
        f"BB({params['bb_period']},{params['bb_std']}) "
        f"[{params['mode']}]"
    )
    result = run_backtest(name, closes, dates, signal_fn)
    results.append(result)

# ── Sort and Display ──────────────────────────────────────────────

print("\n")
print("=" * 120)
print("TOP 15 BY TOTAL RETURN (報酬率)")
print("=" * 120)
print(f"{'#':>3} {'Strategy':<65} {'Return%':>8} {'Ann%':>7} {'MaxDD%':>8} {'Win%':>6} {'Trades':>6} {'PF':>6} {'Sharpe':>7} {'B&H%':>7}")
print("-" * 120)

results_sorted = sorted(results, key=lambda r: r.total_return_pct, reverse=True)
for i, r in enumerate(results_sorted[:15], 1):
    print(
        f"{i:>3} {r.name:<65} {r.total_return_pct:>8.2f} {r.annualized_return_pct:>7.2f} "
        f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {r.total_trades:>6} {r.profit_factor:>6.2f} "
        f"{r.sharpe:>7.4f} {r.buy_hold_return_pct:>7.2f}"
    )

print("\n")
print("=" * 120)
print("TOP 15 BY WIN RATE (勝率)")
print("=" * 120)
print(f"{'#':>3} {'Strategy':<65} {'Return%':>8} {'Ann%':>7} {'MaxDD%':>8} {'Win%':>6} {'Trades':>6} {'PF':>6} {'Sharpe':>7} {'B&H%':>7}")
print("-" * 120)

results_by_win = sorted(
    [r for r in results if r.total_trades >= 4],  # at least 2 round trips
    key=lambda r: r.win_rate_pct,
    reverse=True,
)
for i, r in enumerate(results_by_win[:15], 1):
    print(
        f"{i:>3} {r.name:<65} {r.total_return_pct:>8.2f} {r.annualized_return_pct:>7.2f} "
        f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {r.total_trades:>6} {r.profit_factor:>6.2f} "
        f"{r.sharpe:>7.4f} {r.buy_hold_return_pct:>7.2f}"
    )

print("\n")
print("=" * 120)
print("TOP 15 BY SHARPE RATIO (風險調整報酬)")
print("=" * 120)
print(f"{'#':>3} {'Strategy':<65} {'Return%':>8} {'Ann%':>7} {'MaxDD%':>8} {'Win%':>6} {'Trades':>6} {'PF':>6} {'Sharpe':>7} {'B&H%':>7}")
print("-" * 120)

results_by_sharpe = sorted(
    [r for r in results if r.total_trades >= 4],
    key=lambda r: r.sharpe,
    reverse=True,
)
for i, r in enumerate(results_by_sharpe[:15], 1):
    print(
        f"{i:>3} {r.name:<65} {r.total_return_pct:>8.2f} {r.annualized_return_pct:>7.2f} "
        f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {r.total_trades:>6} {r.profit_factor:>6.2f} "
        f"{r.sharpe:>7.4f} {r.buy_hold_return_pct:>7.2f}"
    )

# ── Best Overall ──────────────────────────────────────────────────

print("\n")
print("=" * 120)
print("BEST OVERALL (報酬 × 勝率 × Sharpe 綜合排名)")
print("=" * 120)

# Composite score: normalize and weight
valid = [r for r in results if r.total_trades >= 4]
if valid:
    max_ret = max(r.total_return_pct for r in valid) or 1
    max_win = max(r.win_rate_pct for r in valid) or 1
    max_sharpe = max(r.sharpe for r in valid) or 1

    scored = []
    for r in valid:
        score = (
            (r.total_return_pct / max_ret) * 0.4
            + (r.win_rate_pct / max_win) * 0.3
            + (r.sharpe / max_sharpe) * 0.3
        )
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"{'#':>3} {'Score':>6} {'Strategy':<65} {'Return%':>8} {'Ann%':>7} {'MaxDD%':>8} {'Win%':>6} {'Trades':>6} {'PF':>6} {'Sharpe':>7}")
    print("-" * 130)
    for i, (sc, r) in enumerate(scored[:10], 1):
        print(
            f"{i:>3} {sc:>6.3f} {r.name:<65} {r.total_return_pct:>8.2f} {r.annualized_return_pct:>7.2f} "
            f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {r.total_trades:>6} {r.profit_factor:>6.2f} "
            f"{r.sharpe:>7.4f}"
        )

    # Print detail of #1
    best = scored[0][1]
    print(f"\n{'='*80}")
    print(f"BEST STRATEGY DETAIL: {best.name}")
    print(f"{'='*80}")
    print(f"  Total Return:     {best.total_return_pct:>8.2f}%")
    print(f"  Annualized:       {best.annualized_return_pct:>8.2f}%")
    print(f"  Max Drawdown:     {best.max_drawdown_pct:>8.2f}%")
    print(f"  Win Rate:         {best.win_rate_pct:>8.2f}%")
    print(f"  Profit Factor:    {best.profit_factor:>8.2f}")
    print(f"  Sharpe Ratio:     {best.sharpe:>8.4f}")
    print(f"  Total Trades:     {best.total_trades:>8}")
    print(f"  Buy & Hold:       {best.buy_hold_return_pct:>8.2f}%")
    print(f"\n  Trade History:")
    for t in best.trades:
        print(f"    {t.date} {t.action:4} @ {t.price:>8.2f} x {t.shares:>6} | {t.reason}")
