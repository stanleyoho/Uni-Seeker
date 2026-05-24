"""
Uni-Seeker Extended Backtest: Novel Strategy Angles for 00631L

Tests strategies NOT covered by the main backtest_toolkit.py grid search:
1. Multi-timeframe BIAS (fast buy / slow sell)
2. Asymmetric RSI (different periods for buy vs sell)
3. BB width filter (volatility gating)
4. RSI divergence-like (recovery detection)
5. BIAS momentum (crossover from below threshold)
6. Trailing stop
7. Consecutive days filter

All strategies reuse calc_* functions and BacktestToolkit from backtest_toolkit.py.
"""

from __future__ import annotations

import os
import sys
import math
import time

# Ensure project root is on path so we can import from scripts/
sys.path.insert(0, os.path.dirname(__file__))

from backtest_toolkit import (
    BacktestToolkit,
    StrategyBuilder,
    calc_rsi,
    calc_bias,
    calc_bollinger,
    calc_ma,
    run_single_backtest,
    SignalFn,
)


# ══════════════════════════════════════════════════════════════════
# Novel Signal Functions
# ══════════════════════════════════════════════════════════════════

def make_multi_timeframe_bias(
    fast_period: int, fast_buy: float,
    slow_period: int, slow_sell: float,
) -> SignalFn:
    """Buy on fast BIAS (short MA), sell on slow BIAS (long MA)."""
    def fn(closes):
        fast_b = calc_bias(closes, fast_period)
        slow_b = calc_bias(closes, slow_period)
        if fast_b is None or slow_b is None:
            return "HOLD", "MT-BIAS not ready"
        if fast_b <= fast_buy:
            return "BUY", f"BIAS({fast_period})={fast_b:.2f}%<={fast_buy}%"
        if slow_b >= slow_sell:
            return "SELL", f"BIAS({slow_period})={slow_b:.2f}%>={slow_sell}%"
        return "HOLD", f"BIAS({fast_period})={fast_b:.2f}%, BIAS({slow_period})={slow_b:.2f}%"
    return fn


def make_asymmetric_rsi(
    buy_period: int, buy_threshold: float,
    sell_period: int, sell_threshold: float,
) -> SignalFn:
    """Different RSI periods for buy vs sell detection."""
    def fn(closes):
        rsi_buy = calc_rsi(closes, buy_period)
        rsi_sell = calc_rsi(closes, sell_period)
        if rsi_buy is None or rsi_sell is None:
            return "HOLD", "Asym-RSI not ready"
        if rsi_buy < buy_threshold:
            return "BUY", f"RSI({buy_period})={rsi_buy:.1f}<{buy_threshold}"
        if rsi_sell > sell_threshold:
            return "SELL", f"RSI({sell_period})={rsi_sell:.1f}>{sell_threshold}"
        return "HOLD", f"RSI({buy_period})={rsi_buy:.1f}, RSI({sell_period})={rsi_sell:.1f}"
    return fn


def make_bb_width_gated(
    inner_fn: SignalFn,
    bb_period: int, bb_std: float, width_threshold: float,
) -> SignalFn:
    """Only allow BUY when BB width > threshold (high volatility = better entry).
    SELL signals pass through unconditionally."""
    def fn(closes):
        action, reason = inner_fn(closes)
        if action == "BUY":
            bb = calc_bollinger(closes, bb_period, bb_std)
            if bb is None:
                return "HOLD", "BB-width not ready"
            lower, middle, upper = bb
            width = (upper - lower) / middle * 100 if middle > 0 else 0
            if width >= width_threshold:
                return "BUY", f"{reason} | BBw={width:.2f}%>={width_threshold}%"
            else:
                return "HOLD", f"BBw={width:.2f}%<{width_threshold}% (filtered)"
        return action, reason
    return fn


def make_rsi_recovery(
    period: int, oversold: float, recovery_delta: float,
    sell_threshold: float,
) -> SignalFn:
    """Buy when RSI was recently oversold AND is now recovering (rising).
    Requires RSI to have been below `oversold` within last 5 bars,
    and current RSI to be `recovery_delta` above its recent minimum."""
    def fn(closes):
        if len(closes) < period + 6:
            return "HOLD", "RSI-recovery not ready"
        # Compute RSI for the last 6 data slices
        recent_rsis = []
        for offset in range(5, -1, -1):
            end_idx = len(closes) - offset
            if end_idx <= period:
                return "HOLD", "RSI-recovery not ready"
            r = calc_rsi(closes[:end_idx], period)
            if r is not None:
                recent_rsis.append(r)
        if len(recent_rsis) < 3:
            return "HOLD", "RSI-recovery insufficient data"
        current_rsi = recent_rsis[-1]
        min_recent = min(recent_rsis)
        # Buy: was oversold recently AND recovering
        if min_recent < oversold and (current_rsi - min_recent) >= recovery_delta:
            return "BUY", f"RSI recovering: min={min_recent:.1f}, now={current_rsi:.1f}, delta={current_rsi - min_recent:.1f}"
        # Sell: standard overbought
        if current_rsi > sell_threshold:
            return "SELL", f"RSI({period})={current_rsi:.1f}>{sell_threshold}"
        return "HOLD", f"RSI({period})={current_rsi:.1f}"
    return fn


def make_bias_momentum(
    period: int, cross_threshold: float, sell_threshold: float,
) -> SignalFn:
    """Buy when BIAS crosses from below threshold to above (recovery momentum).
    Requires previous bar BIAS < threshold AND current BIAS >= threshold."""
    def fn(closes):
        if len(closes) < period + 2:
            return "HOLD", "BIAS-mom not ready"
        bias_now = calc_bias(closes, period)
        bias_prev = calc_bias(closes[:-1], period)
        if bias_now is None or bias_prev is None:
            return "HOLD", "BIAS-mom not ready"
        # Buy on upward cross of threshold
        if bias_prev < cross_threshold and bias_now >= cross_threshold:
            return "BUY", f"BIAS cross up: {bias_prev:.2f}%->{bias_now:.2f}% (thr={cross_threshold}%)"
        # Sell when BIAS too high
        if bias_now >= sell_threshold:
            return "SELL", f"BIAS({period})={bias_now:.2f}%>={sell_threshold}%"
        return "HOLD", f"BIAS({period})={bias_now:.2f}%"
    return fn


def make_consecutive_days_filter(
    inner_fn: SignalFn, n_days: int,
) -> SignalFn:
    """Only trigger BUY if the inner strategy has signalled BUY for N consecutive days.
    Uses a closure to track state across calls."""
    consecutive_buy_count = [0]  # mutable closure

    def fn(closes):
        action, reason = inner_fn(closes)
        if action == "BUY":
            consecutive_buy_count[0] += 1
            if consecutive_buy_count[0] >= n_days:
                return "BUY", f"{reason} | {n_days}d consecutive"
            else:
                return "HOLD", f"BUY day {consecutive_buy_count[0]}/{n_days}"
        else:
            consecutive_buy_count[0] = 0
            return action, reason
    return fn


# ══════════════════════════════════════════════════════════════════
# Trailing Stop Engine (needs custom backtest loop)
# ══════════════════════════════════════════════════════════════════

def run_trailing_stop_backtest(
    name: str,
    params: dict,
    closes: list[float],
    dates: list[str],
    entry_fn: SignalFn,
    trail_pct: float,
    initial_capital: float = 1_000_000,
    position_size: float = 0.95,
    fee_rate: float = 0.001425,
    tax_rate: float = 0.003,
):
    """Custom backtest with trailing stop: after buy, track peak price,
    sell if price drops trail_pct% from peak."""
    from backtest_toolkit import BacktestResult, Trade

    cash = initial_capital
    shares = 0
    trades: list[Trade] = []
    equity_curve: list[float] = []
    buy_price = 0.0
    peak_price = 0.0

    for i in range(1, len(closes)):
        price = closes[i]
        closes_so_far = closes[:i + 1]
        action, reason = entry_fn(closes_so_far)

        # Trailing stop logic
        if shares > 0:
            if price > peak_price:
                peak_price = price
            drop_pct = (peak_price - price) / peak_price * 100
            if drop_pct >= trail_pct:
                action = "SELL"
                reason = f"TRAILING_STOP (peak={peak_price:.2f}, drop={drop_pct:.1f}%>={trail_pct}%)"

        if action == "BUY" and shares == 0:
            invest = cash * position_size
            buy_shares = int(invest / (price * (1 + fee_rate)))
            if buy_shares > 0:
                cost = buy_shares * price * (1 + fee_rate)
                cash -= cost
                shares = buy_shares
                buy_price = price
                peak_price = price
                trades.append(Trade(dates[i], "BUY", price, buy_shares, reason))

        elif action == "SELL" and shares > 0:
            proceeds = shares * price * (1 - fee_rate - tax_rate)
            cash += proceeds
            trades.append(Trade(dates[i], "SELL", price, shares, reason))
            shares = 0
            buy_price = 0.0
            peak_price = 0.0

        equity = cash + shares * price
        equity_curve.append(equity)

    # Force close
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
    peak_eq = equity_curve[0] if equity_curve else initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak_eq:
            peak_eq = val
        dd = (val - peak_eq) / peak_eq * 100
        if dd < max_dd:
            max_dd = dd

    # Win/loss
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
        daily_returns = [(equity_curve[i] / equity_curve[i - 1] - 1)
                         for i in range(1, len(equity_curve)) if equity_curve[i - 1] > 0]
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
# Extended Grid Search
# ══════════════════════════════════════════════════════════════════

def extended_grid_search():
    """Run extended strategy grid search on 00631L."""

    toolkit = BacktestToolkit(symbol="00631L.TW", start="2020-01-01")

    # ── Strategy 1: Multi-timeframe BIAS ────────────────────────────
    print("Adding Strategy 1: Multi-timeframe BIAS...")
    count = 0
    for fast_p in [3, 5, 7]:
        for fast_buy in [-3, -5, -7, -10]:
            for slow_p in [15, 20, 30]:
                for slow_sell in [3, 5, 7, 10]:
                    params = dict(
                        bias_fast_period=fast_p, bias_fast_buy=fast_buy,
                        bias_slow_period=slow_p, bias_slow_sell=slow_sell,
                    )
                    name = f"MT-BIAS buy=BIAS({fast_p})<={fast_buy}% sell=BIAS({slow_p})>={slow_sell}%"
                    fn = make_multi_timeframe_bias(fast_p, fast_buy, slow_p, slow_sell)
                    toolkit.add_strategy(name, fn, params)
                    count += 1
    print(f"  -> {count} combinations")

    # ── Strategy 2: Asymmetric RSI ──────────────────────────────────
    print("Adding Strategy 2: Asymmetric RSI...")
    count = 0
    for buy_p in [5, 7, 10]:
        for buy_thr in [25, 30, 35]:
            for sell_p in [14, 21, 28]:
                for sell_thr in [65, 70, 75, 80]:
                    params = dict(
                        rsi_buy_period=buy_p, rsi_buy=buy_thr,
                        rsi_sell_period=sell_p, rsi_sell=sell_thr,
                    )
                    name = f"AsymRSI buy=RSI({buy_p})<{buy_thr} sell=RSI({sell_p})>{sell_thr}"
                    fn = make_asymmetric_rsi(buy_p, buy_thr, sell_p, sell_thr)
                    toolkit.add_strategy(name, fn, params)
                    count += 1
    print(f"  -> {count} combinations")

    # ── Strategy 3: BB width filter on RSI+BIAS ────────────────────
    print("Adding Strategy 3: BB width filter...")
    count = 0
    for rsi_buy in [30, 35]:
        for rsi_sell in [65, 70]:
            for bias_buy in [-3, -5]:
                for bias_sell in [5, 7]:
                    for bb_std in [2.0, 2.5]:
                        for width_thr in [3, 5, 7, 10]:
                            inner = StrategyBuilder.composite(
                                [
                                    StrategyBuilder.rsi(14, rsi_buy, rsi_sell),
                                    StrategyBuilder.bias(10, bias_buy, bias_sell),
                                ],
                                mode="majority",
                            )
                            fn = make_bb_width_gated(inner, 20, bb_std, width_thr)
                            params = dict(
                                rsi_period=14, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                                bias_period=10, bias_buy=bias_buy, bias_sell=bias_sell,
                                bb_period=20, bb_std=bb_std,
                                bb_width_threshold=width_thr,
                            )
                            name = (
                                f"BBw>={width_thr}% gate RSI(14,{rsi_buy},{rsi_sell})"
                                f"+BIAS(10,{bias_buy},{bias_sell}) bb_std={bb_std}"
                            )
                            toolkit.add_strategy(name, fn, params)
                            count += 1
    print(f"  -> {count} combinations")

    # ── Strategy 4: RSI divergence-like (recovery) ─────────────────
    print("Adding Strategy 4: RSI recovery...")
    count = 0
    for period in [7, 14]:
        for oversold in [25, 30, 35]:
            for delta in [5, 8, 10, 15]:
                for sell_thr in [65, 70, 75]:
                    params = dict(
                        rsi_period=period, rsi_oversold=oversold,
                        rsi_recovery_delta=delta, rsi_sell=sell_thr,
                    )
                    name = f"RSI-recovery({period}) os<{oversold} delta>={delta} sell>{sell_thr}"
                    fn = make_rsi_recovery(period, oversold, delta, sell_thr)
                    toolkit.add_strategy(name, fn, params)
                    count += 1
    print(f"  -> {count} combinations")

    # ── Strategy 5: BIAS momentum (crossover) ──────────────────────
    print("Adding Strategy 5: BIAS momentum...")
    count = 0
    for period in [5, 10, 20]:
        for cross_thr in [-7, -5, -3, -2]:
            for sell_thr in [3, 5, 7, 10]:
                params = dict(
                    bias_period=period,
                    bias_cross_threshold=cross_thr,
                    bias_sell=sell_thr,
                )
                name = f"BIAS-mom({period}) cross>{cross_thr}% sell>={sell_thr}%"
                fn = make_bias_momentum(period, cross_thr, sell_thr)
                toolkit.add_strategy(name, fn, params)
                count += 1
    print(f"  -> {count} combinations")

    # ── Strategy 7: Consecutive days filter on RSI ─────────────────
    print("Adding Strategy 7: Consecutive days filter...")
    count = 0
    for rsi_buy in [30, 35, 40]:
        for rsi_sell in [65, 70, 75]:
            for n_days in [2, 3, 5]:
                inner = StrategyBuilder.rsi(14, rsi_buy, rsi_sell)
                fn = make_consecutive_days_filter(inner, n_days)
                params = dict(
                    rsi_period=14, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                    consecutive_days=n_days,
                )
                name = f"ConsecDays({n_days}) RSI(14,{rsi_buy},{rsi_sell})"
                toolkit.add_strategy(name, fn, params)
                count += 1
    print(f"  -> {count} combinations")

    # Also consecutive days on BIAS
    for bias_buy in [-5, -7]:
        for bias_sell in [5, 7]:
            for n_days in [2, 3]:
                inner = StrategyBuilder.bias(10, bias_buy, bias_sell)
                fn = make_consecutive_days_filter(inner, n_days)
                params = dict(
                    bias_period=10, bias_buy=bias_buy, bias_sell=bias_sell,
                    consecutive_days=n_days,
                )
                name = f"ConsecDays({n_days}) BIAS(10,{bias_buy},{bias_sell})"
                toolkit.add_strategy(name, fn, params)
                count += 1
    print(f"  -> {count} total with BIAS combos")

    # ── Run all standard strategies ─────────────────────────────────
    toolkit.run_all()

    # ── Strategy 6: Trailing stop (custom backtest loop) ───────────
    print("\nRunning Strategy 6: Trailing stop (custom loop)...")
    t0 = time.time()
    trail_count = 0
    for rsi_buy in [30, 35]:
        for rsi_sell in [65, 70, 75]:
            for trail_pct in [5, 8, 10, 15, 20]:
                entry_fn = StrategyBuilder.rsi(14, rsi_buy, rsi_sell)
                params = dict(
                    rsi_period=14, rsi_buy=rsi_buy, rsi_sell=rsi_sell,
                    trailing_stop_pct=trail_pct,
                )
                name = f"TrailStop({trail_pct}%) RSI(14,{rsi_buy},{rsi_sell})"
                result = run_trailing_stop_backtest(
                    name=name,
                    params=params,
                    closes=toolkit.closes,
                    dates=toolkit.dates,
                    entry_fn=entry_fn,
                    trail_pct=trail_pct,
                )
                toolkit.results.append(result)
                trail_count += 1

    # Trailing stop with BIAS entry
    for bias_buy in [-5, -7]:
        for bias_sell in [5, 7]:
            for trail_pct in [5, 8, 10, 15]:
                entry_fn = StrategyBuilder.bias(10, bias_buy, bias_sell)
                params = dict(
                    bias_period=10, bias_buy=bias_buy, bias_sell=bias_sell,
                    trailing_stop_pct=trail_pct,
                )
                name = f"TrailStop({trail_pct}%) BIAS(10,{bias_buy},{bias_sell})"
                result = run_trailing_stop_backtest(
                    name=name,
                    params=params,
                    closes=toolkit.closes,
                    dates=toolkit.dates,
                    entry_fn=entry_fn,
                    trail_pct=trail_pct,
                )
                toolkit.results.append(result)
                trail_count += 1

    print(f"  -> {trail_count} trailing stop combos in {time.time() - t0:.1f}s")

    # ── Export & Leaderboard ────────────────────────────────────────
    output_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "backtest_00631L_extended.csv")

    # Use custom CSV export that includes extended params
    import csv
    headers = [
        "rank_by_return", "strategy_name",
        "rsi_period", "rsi_buy", "rsi_sell",
        "rsi_buy_period", "rsi_sell_period",
        "rsi_oversold", "rsi_recovery_delta",
        "bias_period", "bias_buy", "bias_sell",
        "bias_fast_period", "bias_fast_buy", "bias_slow_period", "bias_slow_sell",
        "bias_cross_threshold",
        "bb_period", "bb_std", "bb_width_threshold",
        "trailing_stop_pct", "consecutive_days",
        "total_return_pct", "annualized_return_pct", "max_drawdown_pct",
        "win_rate_pct", "wins", "losses", "total_trades",
        "profit_factor", "sharpe", "buy_hold_return_pct",
        "backtest_start", "backtest_end", "trading_days",
    ]
    sorted_results = sorted(toolkit.results, key=lambda r: r.total_return_pct, reverse=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for rank, r in enumerate(sorted_results, 1):
            p = r.params
            writer.writerow({
                "rank_by_return": rank,
                "strategy_name": r.name,
                "rsi_period": p.get("rsi_period", ""),
                "rsi_buy": p.get("rsi_buy", ""),
                "rsi_sell": p.get("rsi_sell", ""),
                "rsi_buy_period": p.get("rsi_buy_period", ""),
                "rsi_sell_period": p.get("rsi_sell_period", ""),
                "rsi_oversold": p.get("rsi_oversold", ""),
                "rsi_recovery_delta": p.get("rsi_recovery_delta", ""),
                "bias_period": p.get("bias_period", ""),
                "bias_buy": p.get("bias_buy", ""),
                "bias_sell": p.get("bias_sell", ""),
                "bias_fast_period": p.get("bias_fast_period", ""),
                "bias_fast_buy": p.get("bias_fast_buy", ""),
                "bias_slow_period": p.get("bias_slow_period", ""),
                "bias_slow_sell": p.get("bias_slow_sell", ""),
                "bias_cross_threshold": p.get("bias_cross_threshold", ""),
                "bb_period": p.get("bb_period", ""),
                "bb_std": p.get("bb_std", ""),
                "bb_width_threshold": p.get("bb_width_threshold", ""),
                "trailing_stop_pct": p.get("trailing_stop_pct", ""),
                "consecutive_days": p.get("consecutive_days", ""),
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
    print(f"\nExported {len(sorted_results)} results to {csv_path}")

    toolkit.print_leaderboard(top_n=20)

    return toolkit


if __name__ == "__main__":
    extended_grid_search()
