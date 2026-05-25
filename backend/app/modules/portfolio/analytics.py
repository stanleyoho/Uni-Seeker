"""Portfolio analytics — TWR, Sharpe, max drawdown. Pure functions.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md
      §11 extensibility (TWR / Sharpe mentions) + §6 Table 6 (holdings_snapshots).

Phase 5 (Advanced analytics). No DB, no SQLAlchemy, no FastAPI, no float —
mirrors the pure-module pattern of `pnl.py` / `cost_basis.py`. The service
layer (`app.services.portfolio.analytics_service`) is the only caller and is
responsible for marshalling snapshots / cash-flow rows out of the DB before
delegating math here.

Algorithms (concise references — see analytics_service module docstring for
the longer write-up):

  * TWR — Modified Dietz / sub-period style. Cash-flow timestamps split the
    period into windows; each window contributes
        r_i = (V_end - V_start - F_window) / V_start
    and the period return chains them:
        TWR = Π (1 + r_i) - 1
    Annualised by `(1 + TWR) ** (365 / period_days) - 1`. We do not assume
    flows happen at window boundaries; instead we treat each cash flow as
    closing the prior window at the *nearest* snapshot date and opening a
    new one — see `compute_twr` for the exact boundary contract.

  * Sharpe — `(mean(r) - rf_daily) / stdev(r) * sqrt(252)`. Daily-return
    series (one element per pair of consecutive snapshots). `rf` is supplied
    *annualised*; we divide by 252 to match the trading-day convention used
    by the numerator. `stdev` uses the *sample* (Bessel-corrected) form,
    matching `statistics.stdev` so existing test data is reproducible.

  * Max drawdown — peak-to-trough scan in O(n). Returns both the absolute
    drop and the percentage (negative numbers; 0 means no drawdown).

Decimal everywhere. The square roots in Sharpe / variance are computed via
`Decimal.sqrt()` (newton iteration; deterministic & lossless within the
working precision).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, getcontext

__all__ = [
    "AnalyticsResult",
    "CashFlow",
    "NavSnapshot",
    "compute_max_drawdown",
    "compute_sharpe",
    "compute_twr",
    "daily_returns_from_navs",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TRADING_DAYS_PER_YEAR = Decimal("252")
_CALENDAR_DAYS_PER_YEAR = Decimal("365")
_DEFAULT_RF_ANNUAL = Decimal("0.02")  # 2 % annualised — see compute_sharpe

# Newton iteration via Decimal needs enough precision so chained TWR products
# don't lose digits on small daily returns; 50 digits is more than enough for
# any realistic portfolio horizon (>>30 years).
getcontext().prec = 50


@dataclass(frozen=True)
class CashFlow:
    """External cash flow into / out of the portfolio.

    `amount` is positive for deposits (e.g. a BUY brings principal IN) and
    negative for withdrawals (a SELL brings principal OUT). The service layer
    builds these from `portfolio_trades` rows before calling `compute_twr`.

    `flow_date` is the trade settlement date; we treat the flow as occurring
    *between* the snapshot of that date and the previous snapshot so the
    sub-period split is unambiguous.
    """

    flow_date: date
    amount: Decimal


@dataclass(frozen=True)
class NavSnapshot:
    """Net-asset-value snapshot — one row from `holdings_snapshots`.

    `total_value` is the marked-to-market value (sum of qty × last_price),
    `total_cost` is the FIFO cost basis. Both are Decimal.
    """

    snapshot_date: date
    total_value: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class AnalyticsResult:
    """Output of `AnalyticsService.compute_period_analytics`.

    All numeric fields are Decimal; the API layer translates to string per
    `CLAUDE.md` Decimal-as-string rule. `sharpe_ratio` is `None` when there
    are fewer than 2 snapshots or when realised stdev is exactly zero.
    """

    twr: Decimal
    twr_annualized: Decimal
    sharpe_ratio: Decimal | None
    max_drawdown: Decimal  # absolute (non-positive)
    max_drawdown_pct: Decimal  # percentage (non-positive)
    period_days: int
    snapshot_count: int


# ── TWR ─────────────────────────────────────────────────────────────────────


def compute_twr(
    snapshots: list[NavSnapshot],
    cash_flows: list[CashFlow],
) -> tuple[Decimal, Decimal]:
    """Time-weighted return + annualised TWR.

    Returns `(twr, twr_annualized)`. Both are `Decimal` and may be negative.

    Algorithm (sub-period TWR, a.k.a. unit-value method):
      1. Sort snapshots ASC by date.
      2. For each consecutive (s_prev, s_curr) pair, find the cash flows
         whose `flow_date` is in `(s_prev.snapshot_date, s_curr.snapshot_date]`
         and sum them as `F` (positive = deposit, negative = withdrawal).
      3. Sub-period return:
              r_i = (s_curr.total_value - s_prev.total_value - F) / s_prev.total_value
         skipped (r_i = 0) when `s_prev.total_value == 0` (no capital to earn
         on; cf. docstring "Edge cases").
      4. `TWR = Π(1 + r_i) - 1`. Annualised:
              twr_annualized = (1 + TWR) ** (365 / days) - 1
         where `days = (last - first).days`. Annualisation skipped (= TWR
         verbatim) when `days <= 0` to avoid the 0^x ambiguity.

    Edge cases:
      * `len(snapshots) < 2`     → `(0, 0)` (need ≥ 2 NAV points for a return)
      * `s_prev.total_value == 0` → that sub-period contributes a factor of 1
      * negative `1 + r_i`        → still chained; if the *product* turns
        negative (portfolio wiped out), we return the chained value as-is.
        Annualisation is skipped (returns the unannualised value) when the
        chained product is ≤ 0 because `x ** Decimal(...)` is undefined.
    """
    if not snapshots or len(snapshots) < 2:
        return (_ZERO, _ZERO)

    sorted_snaps = sorted(snapshots, key=lambda s: s.snapshot_date)
    # Defensive copy so we don't mutate the caller's list.
    sorted_flows = sorted(cash_flows, key=lambda f: f.flow_date)

    product = _ONE
    for i in range(1, len(sorted_snaps)):
        s_prev = sorted_snaps[i - 1]
        s_curr = sorted_snaps[i]
        # Sum cash flows strictly *after* prev (exclusive) and ≤ curr
        # (inclusive). This matches the "flow happened during this window"
        # invariant — a BUY on date D belongs to the window ending on D.
        window_flow = _ZERO
        for f in sorted_flows:
            if s_prev.snapshot_date < f.flow_date <= s_curr.snapshot_date:
                window_flow += f.amount

        start_value = s_prev.total_value
        if start_value == _ZERO:
            # No capital at start of window → undefined return; treat as 0.
            continue

        end_value = s_curr.total_value
        sub_return = (end_value - start_value - window_flow) / start_value
        product = product * (_ONE + sub_return)

    twr = product - _ONE

    # Annualise (calendar days, per spec §11 mention)
    period_days = (sorted_snaps[-1].snapshot_date - sorted_snaps[0].snapshot_date).days
    if period_days <= 0 or product <= _ZERO:
        # No annualisation possible (single-day window or wiped-out portfolio).
        return (twr, twr)

    exponent = _CALENDAR_DAYS_PER_YEAR / Decimal(period_days)
    # Decimal does not implement non-integer exponentiation natively for
    # arbitrary precision; we go through ln/exp.
    twr_ann = (product.ln() * exponent).exp() - _ONE
    return (twr, twr_ann)


# ── Sharpe ──────────────────────────────────────────────────────────────────


def daily_returns_from_navs(snapshots: list[NavSnapshot]) -> list[Decimal]:
    """Convert NAV time-series → daily simple returns.

    `r_t = (V_t - V_{t-1}) / V_{t-1}`; entries with `V_{t-1} == 0` produce
    `0` (cannot compound on zero capital).

    Returned list has `len(snapshots) - 1` entries (or 0 when input is empty
    or single-row).
    """
    if not snapshots or len(snapshots) < 2:
        return []

    sorted_snaps = sorted(snapshots, key=lambda s: s.snapshot_date)
    out: list[Decimal] = []
    for i in range(1, len(sorted_snaps)):
        prev_v = sorted_snaps[i - 1].total_value
        curr_v = sorted_snaps[i].total_value
        if prev_v == _ZERO:
            out.append(_ZERO)
        else:
            out.append((curr_v - prev_v) / prev_v)
    return out


def compute_sharpe(
    returns: list[Decimal],
    risk_free_rate: Decimal = _DEFAULT_RF_ANNUAL,
) -> Decimal | None:
    """Sharpe ratio (annualised) for a series of *daily* returns.

    ``sharpe = (mean(r) - rf_daily) / stdev(r) * sqrt(252)``

    Where `rf_daily = risk_free_rate / 252` so the numerator is already
    expressed per trading day, then we scale up by `sqrt(252)` to get the
    annualised figure (standard quant convention).

    Args:
        returns: Daily *simple* returns (not log). Typically produced by
            `daily_returns_from_navs(snapshots)`.
        risk_free_rate: Annualised risk-free rate as a Decimal fraction.
            Default 0.02 (= 2 % p.a.) tracks the U.S. 1-yr T-bill ~ Q2 2026.
            Service layer may override via config later.

    Returns:
        Decimal Sharpe value, or `None` when:
          * `len(returns) < 2` (need ≥ 2 points to estimate stdev)
          * `stdev == 0` (constant returns → infinite Sharpe is meaningless)
    """
    n = len(returns)
    if n < 2:
        return None

    n_dec = Decimal(n)
    mean = sum(returns, _ZERO) / n_dec

    # Sample variance (Bessel-corrected): Σ(r - mean)² / (n - 1)
    sq_diff_sum = sum((r - mean) ** 2 for r in returns)
    variance = sq_diff_sum / (n_dec - _ONE)
    if variance <= _ZERO:
        return None
    stdev = variance.sqrt()
    if stdev == _ZERO:
        return None

    rf_daily = risk_free_rate / _TRADING_DAYS_PER_YEAR
    sqrt_252 = _TRADING_DAYS_PER_YEAR.sqrt()
    return (mean - rf_daily) / stdev * sqrt_252


# ── Max drawdown ────────────────────────────────────────────────────────────


def compute_max_drawdown(navs: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Peak-to-trough max drawdown.

    Returns `(max_drawdown_absolute, max_drawdown_pct)`. Both are
    *non-positive* Decimals (0 means no drawdown, e.g. monotonically
    increasing series).

    Algorithm (O(n)):
      * `peak`         = running max of NAV seen so far
      * `drawdown`     = `nav - peak`            (≤ 0)
      * `drawdown_pct` = `(nav - peak) / peak`   (≤ 0)
      * Track the most negative pair across the scan.

    Edge cases:
      * empty list           → `(0, 0)`
      * single element       → `(0, 0)` (no peak vs. trough to compare)
      * peak == 0 mid-stream → pct skipped for that point (uses 0)
        — should not happen on a real portfolio but guards against div/0.
    """
    if not navs or len(navs) < 2:
        return (_ZERO, _ZERO)

    peak = navs[0]
    max_dd_abs = _ZERO
    max_dd_pct = _ZERO

    for nav in navs[1:]:
        if nav > peak:
            peak = nav
            continue
        dd_abs = nav - peak  # ≤ 0
        dd_pct = _ZERO if peak == _ZERO else dd_abs / peak  # ≤ 0
        if dd_abs < max_dd_abs:
            max_dd_abs = dd_abs
        if dd_pct < max_dd_pct:
            max_dd_pct = dd_pct

    return (max_dd_abs, max_dd_pct)
