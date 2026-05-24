"""
Uni-Seeker 回測工具箱 (Backtest Toolkit)

可重用的回測框架，支援：
- 任意台股/ETF 標的（透過 yfinance）
- 單一或複合策略
- 參數網格搜尋
- 停損停利機制
- 結果輸出 CSV
- 排行榜 + 最佳策略詳情

Usage:
    from scripts.backtest_toolkit import BacktestToolkit, StrategyBuilder

    toolkit = BacktestToolkit(symbol="00631L.TW", start="2020-01-01")
    toolkit.add_strategy("RSI+BB+BIAS", StrategyBuilder.composite(
        ["rsi", "bollinger", "bias"], mode="all",
        rsi_buy=35, rsi_sell=70, bias_buy=-3, bias_sell=7, bb_std=2.5,
    ))
    toolkit.run_all()
    toolkit.export_csv("results.csv")
    toolkit.print_leaderboard()
"""

from __future__ import annotations

import csv
import itertools
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import yfinance as yf


# ══════════════════════════════════════════════════════════════════
# Indicator Calculations
# ══════════════════════════════════════════════════════════════════

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
    return sma - num_std * std, sma, sma + num_std * std


def calc_kd(highs: list[float], lows: list[float], closes: list[float], period: int = 9) -> tuple[float, float] | None:
    if len(closes) < period:
        return None
    h_window = highs[-period:]
    l_window = lows[-period:]
    highest = max(h_window)
    lowest = min(l_window)
    if highest == lowest:
        return 50.0, 50.0
    rsv = (closes[-1] - lowest) / (highest - lowest) * 100
    # Simplified: use RSV as K approximation, K*2/3 as D
    k = rsv
    d = k * 2 / 3 + 50 / 3  # smoothed approximation
    return k, d


def calc_macd(data: list[float], fast: int = 12, slow: int = 26) -> tuple[float, float] | None:
    """Returns (macd_line, signal_approx) using SMA approximation for speed."""
    if len(data) < slow + 9:
        return None
    fast_ma = sum(data[-fast:]) / fast
    slow_ma = sum(data[-slow:]) / slow
    macd_now = fast_ma - slow_ma
    # Signal approximation: MACD of 9 periods ago
    if len(data) >= slow + 9:
        prev_data = data[:-9]
        prev_fast = sum(prev_data[-fast:]) / fast
        prev_slow = sum(prev_data[-slow:]) / slow
        signal_approx = prev_fast - prev_slow
        return macd_now, signal_approx
    return macd_now, 0.0


def calc_ma(data: list[float], period: int) -> float | None:
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


# ══════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════

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
    params: dict
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    wins: int
    losses: int
    profit_factor: float
    sharpe: float
    buy_hold_return_pct: float
    backtest_start: str
    backtest_end: str
    trading_days: int
    trades: list[Trade] = field(default_factory=list)


SignalFn = Callable[[list[float]], tuple[str, str]]
SignalFnFull = Callable[[list[float], list[float], list[float]], tuple[str, str]]


# ══════════════════════════════════════════════════════════════════
# Backtest Engine
# ══════════════════════════════════════════════════════════════════

def run_single_backtest(
    name: str,
    params: dict,
    closes: list[float],
    dates: list[str],
    signal_fn: SignalFn,
    initial_capital: float = 1_000_000,
    position_size: float = 0.95,
    fee_rate: float = 0.001425,
    tax_rate: float = 0.003,
    stop_loss: float | None = None,
    take_profit: float | None = None,
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

        # Stop loss / take profit override
        if shares > 0 and buy_price > 0:
            pnl_pct = (price - buy_price) / buy_price * 100
            if stop_loss is not None and pnl_pct <= -abs(stop_loss):
                action = "SELL"
                reason = f"STOP_LOSS ({pnl_pct:.1f}% <= -{abs(stop_loss)}%)"
            elif take_profit is not None and pnl_pct >= abs(take_profit):
                action = "SELL"
                reason = f"TAKE_PROFIT ({pnl_pct:.1f}% >= +{abs(take_profit)}%)"

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
            buy_price = 0.0

        equity = cash + shares * price
        equity_curve.append(equity)

    # Force close if still holding
    if shares > 0:
        final_price = closes[-1]
        proceeds = shares * final_price * (1 - fee_rate - tax_rate)
        cash += proceeds
        trades.append(Trade(dates[-1], "SELL(force)", final_price, shares, "End of backtest"))
        shares = 0
        equity_curve[-1] = cash

    final_equity = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_equity / initial_capital - 1) * 100
    n_days = len(equity_curve)
    years = n_days / 252
    ann_return = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 and final_equity > 0 else 0

    # Max drawdown
    peak = equity_curve[0] if equity_curve else initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # Win/loss tracking
    sell_trades = [t for t in trades if t.action in ("SELL", "SELL(force)")]
    buy_trades = [t for t in trades if t.action == "BUY"]
    wins = 0
    loss_count = 0
    total_profit = 0.0
    total_loss = 0.0
    for j, st in enumerate(sell_trades):
        if j < len(buy_trades):
            pnl = (st.price - buy_trades[j].price) * st.shares
            if pnl > 0:
                wins += 1
                total_profit += pnl
            else:
                loss_count += 1
                total_loss += abs(pnl)
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0
    profit_factor = (total_profit / total_loss) if total_loss > 0 else (999 if total_profit > 0 else 0)

    # Sharpe
    if len(equity_curve) > 1:
        daily_returns = [(equity_curve[i] / equity_curve[i - 1] - 1) for i in range(1, len(equity_curve)) if equity_curve[i - 1] > 0]
        if daily_returns:
            avg_r = sum(daily_returns) / len(daily_returns)
            std_r = math.sqrt(sum((r - avg_r) ** 2 for r in daily_returns) / len(daily_returns))
            sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    buy_hold = (closes[-1] / closes[0] - 1) * 100

    return BacktestResult(
        name=name,
        params=params,
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(ann_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 2),
        total_trades=len(trades),
        wins=wins,
        losses=loss_count,
        profit_factor=round(min(profit_factor, 999), 2),
        sharpe=round(sharpe, 4),
        buy_hold_return_pct=round(buy_hold, 2),
        backtest_start=dates[0],
        backtest_end=dates[-1],
        trading_days=n_days,
        trades=trades,
    )


# ══════════════════════════════════════════════════════════════════
# Strategy Signal Builders
# ══════════════════════════════════════════════════════════════════

class StrategyBuilder:
    """Factory for creating signal functions."""

    @staticmethod
    def rsi(period=14, buy=30, sell=70) -> SignalFn:
        def fn(closes):
            rsi = calc_rsi(closes, period)
            if rsi is None:
                return "HOLD", "RSI not ready"
            if rsi < buy:
                return "BUY", f"RSI={rsi:.1f}<{buy}"
            if rsi > sell:
                return "SELL", f"RSI={rsi:.1f}>{sell}"
            return "HOLD", f"RSI={rsi:.1f}"
        return fn

    @staticmethod
    def bias(period=20, buy=-5, sell=5) -> SignalFn:
        def fn(closes):
            b = calc_bias(closes, period)
            if b is None:
                return "HOLD", "BIAS not ready"
            if b <= buy:
                return "BUY", f"BIAS={b:.2f}%<={buy}%"
            if b >= sell:
                return "SELL", f"BIAS={b:.2f}%>={sell}%"
            return "HOLD", f"BIAS={b:.2f}%"
        return fn

    @staticmethod
    def bollinger(period=20, std=2.0) -> SignalFn:
        def fn(closes):
            bb = calc_bollinger(closes, period, std)
            if bb is None:
                return "HOLD", "BB not ready"
            lower, middle, upper = bb
            price = closes[-1]
            if price <= lower:
                return "BUY", f"Price<BB_lower({lower:.2f})"
            if price >= upper:
                return "SELL", f"Price>BB_upper({upper:.2f})"
            return "HOLD", f"Price in BB"
        return fn

    @staticmethod
    def macd(fast=12, slow=26) -> SignalFn:
        def fn(closes):
            result = calc_macd(closes, fast, slow)
            if result is None:
                return "HOLD", "MACD not ready"
            macd_val, signal_val = result
            if macd_val > signal_val and macd_val > 0:
                return "BUY", f"MACD={macd_val:.4f}>signal"
            if macd_val < signal_val and macd_val < 0:
                return "SELL", f"MACD={macd_val:.4f}<signal"
            return "HOLD", f"MACD={macd_val:.4f}"
        return fn

    @staticmethod
    def kd(period=9, buy=20, sell=80) -> SignalFn:
        def fn(closes):
            # KD needs high/low, approximate with closes
            kd = calc_kd(closes, closes, closes, period)
            if kd is None:
                return "HOLD", "KD not ready"
            k, d = kd
            if k < buy and k < d:
                return "BUY", f"K={k:.1f}<{buy},D={d:.1f}"
            if k > sell and k > d:
                return "SELL", f"K={k:.1f}>{sell},D={d:.1f}"
            return "HOLD", f"K={k:.1f},D={d:.1f}"
        return fn

    @staticmethod
    def ma_crossover(short=5, long=20) -> SignalFn:
        def fn(closes):
            if len(closes) < long + 1:
                return "HOLD", "MA not ready"
            short_now = sum(closes[-short:]) / short
            long_now = sum(closes[-long:]) / long
            short_prev = sum(closes[-short - 1:-1]) / short
            long_prev = sum(closes[-long - 1:-1]) / long
            if short_prev <= long_prev and short_now > long_now:
                return "BUY", f"MA({short}) cross above MA({long})"
            if short_prev >= long_prev and short_now < long_now:
                return "SELL", f"MA({short}) cross below MA({long})"
            return "HOLD", "No MA crossover"
        return fn

    @staticmethod
    def composite(sub_fns: list[SignalFn], mode: str = "majority") -> SignalFn:
        def fn(closes):
            signals = []
            reasons = []
            for sub_fn in sub_fns:
                action, reason = sub_fn(closes)
                signals.append(action)
                if action != "HOLD":
                    reasons.append(reason)

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
        return fn


# ══════════════════════════════════════════════════════════════════
# Backtest Toolkit (Main Interface)
# ══════════════════════════════════════════════════════════════════

class BacktestToolkit:
    def __init__(
        self,
        symbol: str,
        start: str = "2020-01-01",
        end: str | None = None,
        initial_capital: float = 1_000_000,
        position_size: float = 0.95,
        fee_rate: float = 0.001425,
        tax_rate: float = 0.003,
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.results: list[BacktestResult] = []
        self._strategies: list[tuple[str, dict, SignalFn, float | None, float | None]] = []

        # Download data
        ticker = symbol if ".TW" in symbol or ".TWO" in symbol else f"{symbol}.TW"
        print(f"Downloading {ticker} data...")
        kwargs = {"start": start, "auto_adjust": True}
        if end:
            kwargs["end"] = end
        df = yf.download(ticker, **kwargs)
        close_series = df["Close"].squeeze().dropna()
        self.closes = [float(c) for c in close_series.values]
        self.dates = [str(d.date()) for d in close_series.index]
        self.start_date = self.dates[0]
        self.end_date = self.dates[-1]
        print(f"Loaded {len(self.closes)} trading days: {self.start_date} ~ {self.end_date}")
        print(f"Price range: {min(self.closes):.2f} ~ {max(self.closes):.2f}\n")

    def add_strategy(
        self,
        name: str,
        signal_fn: SignalFn,
        params: dict | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ):
        self._strategies.append((name, params or {}, signal_fn, stop_loss, take_profit))

    def run_all(self) -> list[BacktestResult]:
        print(f"Running {len(self._strategies)} strategies...")
        t0 = time.time()
        for i, (name, params, fn, sl, tp) in enumerate(self._strategies):
            result = run_single_backtest(
                name=name,
                params=params,
                closes=self.closes,
                dates=self.dates,
                signal_fn=fn,
                initial_capital=self.initial_capital,
                position_size=self.position_size,
                fee_rate=self.fee_rate,
                tax_rate=self.tax_rate,
                stop_loss=sl,
                take_profit=tp,
            )
            self.results.append(result)
            if (i + 1) % 500 == 0:
                print(f"  ...completed {i + 1}/{len(self._strategies)}")
        elapsed = time.time() - t0
        print(f"Done! {len(self.results)} backtests in {elapsed:.1f}s\n")
        return self.results

    def export_csv(self, path: str):
        if not self.results:
            print("No results to export.")
            return
        headers = [
            "rank_by_return", "strategy_name", "mode", "rsi_period", "rsi_buy", "rsi_sell",
            "bias_period", "bias_buy", "bias_sell", "bb_period", "bb_std",
            "macd_fast", "macd_slow", "kd_period", "kd_buy", "kd_sell",
            "ma_short", "ma_long", "stop_loss", "take_profit",
            "total_return_pct", "annualized_return_pct", "max_drawdown_pct",
            "win_rate_pct", "wins", "losses", "total_trades",
            "profit_factor", "sharpe", "buy_hold_return_pct",
            "backtest_start", "backtest_end", "trading_days",
        ]
        sorted_results = sorted(self.results, key=lambda r: r.total_return_pct, reverse=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for rank, r in enumerate(sorted_results, 1):
                p = r.params
                writer.writerow({
                    "rank_by_return": rank,
                    "strategy_name": r.name,
                    "mode": p.get("mode", ""),
                    "rsi_period": p.get("rsi_period", ""),
                    "rsi_buy": p.get("rsi_buy", ""),
                    "rsi_sell": p.get("rsi_sell", ""),
                    "bias_period": p.get("bias_period", ""),
                    "bias_buy": p.get("bias_buy", ""),
                    "bias_sell": p.get("bias_sell", ""),
                    "bb_period": p.get("bb_period", ""),
                    "bb_std": p.get("bb_std", ""),
                    "macd_fast": p.get("macd_fast", ""),
                    "macd_slow": p.get("macd_slow", ""),
                    "kd_period": p.get("kd_period", ""),
                    "kd_buy": p.get("kd_buy", ""),
                    "kd_sell": p.get("kd_sell", ""),
                    "ma_short": p.get("ma_short", ""),
                    "ma_long": p.get("ma_long", ""),
                    "stop_loss": p.get("stop_loss", ""),
                    "take_profit": p.get("take_profit", ""),
                    "total_return_pct": r.total_return_pct,
                    "annualized_return_pct": r.annualized_return_pct,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "win_rate_pct": r.win_rate_pct,
                    "wins": r.wins,
                    "losses": r.losses,
                    "total_trades": r.total_trades,
                    "profit_factor": r.profit_factor,
                    "sharpe": r.sharpe,
                    "buy_hold_return_pct": r.buy_hold_return_pct,
                    "backtest_start": r.backtest_start,
                    "backtest_end": r.backtest_end,
                    "trading_days": r.trading_days,
                })
        print(f"Exported {len(sorted_results)} results to {path}")

    def print_leaderboard(self, top_n: int = 15, min_trades: int = 4):
        valid = [r for r in self.results if r.total_trades >= min_trades]
        if not valid:
            print("No results with enough trades.")
            return

        print("=" * 130)
        print(f"  回測標的: {self.symbol}")
        print(f"  回測期間: {self.start_date} ~ {self.end_date} ({len(self.closes)} 交易日, {len(self.closes)/252:.1f} 年)")
        print(f"  初始資金: {self.initial_capital:,.0f}")
        print(f"  參數組合: {len(self.results)} | 有效交易(>={min_trades}筆): {len(valid)}")
        print(f"  買入持有: {self.results[0].buy_hold_return_pct:.2f}%")
        print("=" * 130)

        def _print_table(title, sorted_list):
            print(f"\n{'─'*130}")
            print(f"  {title}")
            print(f"{'─'*130}")
            print(f"  {'#':>3} {'Strategy':<55} {'Return%':>9} {'Ann%':>8} {'MaxDD%':>8} {'Win%':>6} {'W/L':>7} {'Trades':>6} {'PF':>7} {'Sharpe':>7}")
            print(f"  {'-'*3} {'-'*55} {'-'*9} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*7}")
            for i, r in enumerate(sorted_list[:top_n], 1):
                wl = f"{r.wins}/{r.losses}"
                print(
                    f"  {i:>3} {r.name:<55} {r.total_return_pct:>9.2f} {r.annualized_return_pct:>8.2f} "
                    f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {wl:>7} {r.total_trades:>6} "
                    f"{r.profit_factor:>7.2f} {r.sharpe:>7.4f}"
                )

        # By return
        by_return = sorted(valid, key=lambda r: r.total_return_pct, reverse=True)
        _print_table("TOP BY TOTAL RETURN (總報酬率)", by_return)

        # By win rate
        by_win = sorted(valid, key=lambda r: (r.win_rate_pct, r.total_return_pct), reverse=True)
        _print_table("TOP BY WIN RATE (勝率)", by_win)

        # By Sharpe
        by_sharpe = sorted(valid, key=lambda r: r.sharpe, reverse=True)
        _print_table("TOP BY SHARPE RATIO (風險調整報酬)", by_sharpe)

        # Composite score
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

        print(f"\n{'─'*130}")
        print(f"  BEST OVERALL (綜合排名: 報酬40% + 勝率30% + Sharpe30%)")
        print(f"{'─'*130}")
        print(f"  {'#':>3} {'Score':>6} {'Strategy':<55} {'Return%':>9} {'Ann%':>8} {'MaxDD%':>8} {'Win%':>6} {'W/L':>7} {'Sharpe':>7}")
        print(f"  {'-'*3} {'-'*6} {'-'*55} {'-'*9} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*7}")
        for i, (sc, r) in enumerate(scored[:top_n], 1):
            wl = f"{r.wins}/{r.losses}"
            print(
                f"  {i:>3} {sc:>6.3f} {r.name:<55} {r.total_return_pct:>9.2f} {r.annualized_return_pct:>8.2f} "
                f"{r.max_drawdown_pct:>8.2f} {r.win_rate_pct:>6.1f} {wl:>7} {r.sharpe:>7.4f}"
            )

        # Detail of #1
        best = scored[0][1]
        print(f"\n{'='*80}")
        print(f"  BEST STRATEGY DETAIL")
        print(f"{'='*80}")
        print(f"  Name:           {best.name}")
        print(f"  Params:         {best.params}")
        print(f"  Total Return:   {best.total_return_pct:>10.2f}%")
        print(f"  Annualized:     {best.annualized_return_pct:>10.2f}%")
        print(f"  Max Drawdown:   {best.max_drawdown_pct:>10.2f}%")
        print(f"  Win Rate:       {best.win_rate_pct:>10.2f}% ({best.wins}W / {best.losses}L)")
        print(f"  Profit Factor:  {best.profit_factor:>10.2f}")
        print(f"  Sharpe Ratio:   {best.sharpe:>10.4f}")
        print(f"  Total Trades:   {best.total_trades:>10}")
        print(f"  Buy & Hold:     {best.buy_hold_return_pct:>10.2f}%")
        print(f"  Period:         {best.backtest_start} ~ {best.backtest_end} ({best.trading_days} days)")
        print(f"\n  Trade History:")
        for t in best.trades:
            print(f"    {t.date}  {t.action:<12} @ {t.price:>10.2f} x {t.shares:>8,} | {t.reason}")


# ══════════════════════════════════════════════════════════════════
# Grid Search Helper
# ══════════════════════════════════════════════════════════════════

def grid_search_00631L():
    """Run comprehensive grid search on 00631L with expanded strategy space."""

    toolkit = BacktestToolkit(symbol="00631L.TW", start="2020-01-01")

    # ── Phase 1: RSI + BIAS + BB 三指標複合 ──────────────────────
    for rsi_buy in [25, 30, 35, 40]:
        for rsi_sell in [60, 65, 70, 75, 80]:
            for bias_period in [5, 10, 20]:
                for bias_buy in [-3, -5, -7, -10]:
                    for bias_sell in [3, 5, 7, 10]:
                        for bb_std in [1.5, 2.0, 2.5]:
                            for mode in ["all", "majority", "any"]:
                                params = dict(
                                    rsi_period=14, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                                    bias_period=bias_period, bias_buy=bias_buy, bias_sell=bias_sell,
                                    bb_period=20, bb_std=bb_std, mode=mode,
                                )
                                name = (
                                    f"RSI(14,{rsi_buy},{rsi_sell})"
                                    f"+BIAS({bias_period},{bias_buy},{bias_sell})"
                                    f"+BB(20,{bb_std})"
                                    f" [{mode}]"
                                )
                                fn = StrategyBuilder.composite(
                                    [
                                        StrategyBuilder.rsi(14, rsi_buy, rsi_sell),
                                        StrategyBuilder.bias(bias_period, bias_buy, bias_sell),
                                        StrategyBuilder.bollinger(20, bb_std),
                                    ],
                                    mode=mode,
                                )
                                toolkit.add_strategy(name, fn, params)

    # ── Phase 2: RSI + BIAS + BB + 停損停利 ──────────────────────
    for sl in [10, 15, 20]:
        for tp in [30, 50, 80]:
            params = dict(
                rsi_period=14, rsi_buy=35, rsi_sell=70,
                bias_period=10, bias_buy=-3, bias_sell=7,
                bb_period=20, bb_std=2.5, mode="all",
                stop_loss=sl, take_profit=tp,
            )
            name = f"RSI+BIAS+BB [all] SL={sl}% TP={tp}%"
            fn = StrategyBuilder.composite(
                [
                    StrategyBuilder.rsi(14, 35, 70),
                    StrategyBuilder.bias(10, -3, 7),
                    StrategyBuilder.bollinger(20, 2.5),
                ],
                mode="all",
            )
            toolkit.add_strategy(name, fn, params, stop_loss=sl, take_profit=tp)

    # ── Phase 3: MACD + RSI 複合 ─────────────────────────────────
    for rsi_buy in [30, 35]:
        for rsi_sell in [65, 70, 75]:
            for mode in ["all", "majority"]:
                params = dict(
                    rsi_period=14, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                    macd_fast=12, macd_slow=26, mode=mode,
                )
                name = f"MACD(12,26)+RSI(14,{rsi_buy},{rsi_sell}) [{mode}]"
                fn = StrategyBuilder.composite(
                    [
                        StrategyBuilder.macd(12, 26),
                        StrategyBuilder.rsi(14, rsi_buy, rsi_sell),
                    ],
                    mode=mode,
                )
                toolkit.add_strategy(name, fn, params)

    # ── Phase 4: KD + RSI + BIAS 複合 ────────────────────────────
    for kd_buy in [20, 25]:
        for kd_sell in [75, 80]:
            for bias_buy in [-3, -5]:
                for bias_sell in [5, 7]:
                    for mode in ["all", "majority"]:
                        params = dict(
                            kd_period=9, kd_buy=kd_buy, kd_sell=kd_sell,
                            rsi_period=14, rsi_buy=30, rsi_sell=70,
                            bias_period=10, bias_buy=bias_buy, bias_sell=bias_sell,
                            mode=mode,
                        )
                        name = f"KD(9,{kd_buy},{kd_sell})+RSI(14,30,70)+BIAS(10,{bias_buy},{bias_sell}) [{mode}]"
                        fn = StrategyBuilder.composite(
                            [
                                StrategyBuilder.kd(9, kd_buy, kd_sell),
                                StrategyBuilder.rsi(14, 30, 70),
                                StrategyBuilder.bias(10, bias_buy, bias_sell),
                            ],
                            mode=mode,
                        )
                        toolkit.add_strategy(name, fn, params)

    # ── Phase 5: MA交叉 + BB + BIAS 複合 ─────────────────────────
    for short in [5, 10]:
        for long in [20, 60]:
            for bb_std in [2.0, 2.5]:
                for mode in ["all", "majority"]:
                    params = dict(
                        ma_short=short, ma_long=long,
                        bb_period=20, bb_std=bb_std,
                        bias_period=10, bias_buy=-5, bias_sell=5,
                        mode=mode,
                    )
                    name = f"MA({short},{long})+BB(20,{bb_std})+BIAS(10,-5,5) [{mode}]"
                    fn = StrategyBuilder.composite(
                        [
                            StrategyBuilder.ma_crossover(short, long),
                            StrategyBuilder.bollinger(20, bb_std),
                            StrategyBuilder.bias(10, -5, 5),
                        ],
                        mode=mode,
                    )
                    toolkit.add_strategy(name, fn, params)

    # ── Phase 6: 四指標超級複合 ───────────────────────────────────
    for mode in ["all", "majority"]:
        for rsi_buy in [30, 35]:
            for bias_buy in [-3, -5]:
                params = dict(
                    rsi_period=14, rsi_buy=rsi_buy, rsi_sell=70,
                    bias_period=10, bias_buy=bias_buy, bias_sell=7,
                    bb_period=20, bb_std=2.5,
                    macd_fast=12, macd_slow=26,
                    mode=mode,
                )
                name = f"RSI+BIAS+BB+MACD [{mode}] rsi_buy={rsi_buy},bias_buy={bias_buy}"
                fn = StrategyBuilder.composite(
                    [
                        StrategyBuilder.rsi(14, rsi_buy, 70),
                        StrategyBuilder.bias(10, bias_buy, 7),
                        StrategyBuilder.bollinger(20, 2.5),
                        StrategyBuilder.macd(12, 26),
                    ],
                    mode=mode,
                )
                toolkit.add_strategy(name, fn, params)

    # Run everything
    toolkit.run_all()

    # Export
    output_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "backtest_00631L_results.csv")
    toolkit.export_csv(csv_path)
    toolkit.print_leaderboard(top_n=20)

    return toolkit


if __name__ == "__main__":
    grid_search_00631L()
