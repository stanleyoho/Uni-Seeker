"""Capital gains tax report — pure module.

Phase 4+ tax export: generates Form 8949-style matched buy-sell pairs
from a trade log + lot-history projection. Computes per-pair gain/loss
plus US holding-period classification (SHORT vs LONG term) and an
annual rollup mirroring Schedule D's short / long term sections.

**No DB, no SQLAlchemy.** Inputs are plain dicts so the module is
trivially testable and reusable from CLI / batch contexts. The service
layer (`app.services.portfolio.tax_report_service`) is responsible for
projecting ORM rows into the dict shape this module consumes.

US tax convention (IRS Pub. 550):
    holding_period_days = (sale_date - acquisition_date).days
    holding_period_days >  365  → LONG term
    holding_period_days <= 365  → SHORT term (incl. same-day = 0 days)

The "more than one year" rule is interpreted as strictly greater than
365 calendar days. A buy on 2024-05-19 and a sale on 2025-05-19 is
exactly 365 days → SHORT. A sale on 2025-05-20 is 366 days → LONG.
This matches the IRS interpretation of "holding period begins the day
after acquisition" (Pub. 550 ch. 4).

FIFO matching:
    For each SELL, consume from a deque of (oldest first) BUY lots,
    emit one `TaxLotMatch` per buy-lot touched. A single SELL across
    three BUYs produces three rows on Form 8949 (per IRS instructions).

Fee/tax allocation (proportional):
    cost_basis  = buy_price * matched_qty + buy_fee * (matched_qty / buy_original_qty)
    proceeds    = sell_price * matched_qty - (sell_fee + sell_tax)
                  * (matched_qty / sell_total_qty)
    gain_loss   = proceeds - cost_basis

Wash-sale flag (`is_wash_sale`) is a placeholder column for Phase 4+;
the loss-disallow detection requires looking ahead 30 calendar days
for a replacement buy of the same security, which is out of scope for
this PR. The column is always False today, kept on the dataclass so
downstream CSV consumers see the canonical Form 8949 column layout.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

__all__ = [
    "TaxLotMatch",
    "TaxYearSummary",
    "classify_holding_period",
    "compute_matched_pairs",
    "summarize_by_year",
]


# Long-term / short-term cutoff. Strictly greater than this many days is LONG.
_LONG_TERM_THRESHOLD_DAYS = 365


@dataclass(frozen=True)
class TaxLotMatch:
    """One matched buy-sell pair = one Form 8949 row.

    Per IRS Form 8949 instructions, every SELL is decomposed into one
    row per distinct acquisition lot consumed. The `term` column drives
    which Form 8949 section (Box A/B/C for short-term, Box D/E/F for
    long-term) the row lands in.
    """

    symbol: str
    market: str
    quantity: Decimal
    acquisition_date: date
    sale_date: date
    cost_basis: Decimal          # original BUY price * matched_qty + allocated fee
    proceeds: Decimal            # SELL price * matched_qty - allocated fee/tax
    gain_loss: Decimal           # proceeds - cost_basis
    holding_period_days: int
    term: str                    # "SHORT" or "LONG"
    is_wash_sale: bool           # Phase 4+ placeholder — always False today


@dataclass(frozen=True)
class TaxYearSummary:
    """Annual rollup mirroring Schedule D Part I (short) + Part II (long)."""

    tax_year: int
    short_term_gain: Decimal
    short_term_loss: Decimal
    short_term_net: Decimal
    long_term_gain: Decimal
    long_term_loss: Decimal
    long_term_net: Decimal
    total_net: Decimal
    total_matches: int


def classify_holding_period(
    acquisition_date: date, sale_date: date
) -> tuple[str, int]:
    """Return (term, days) where term is "SHORT" or "LONG".

    `days = (sale_date - acquisition_date).days`. Same-day sale → 0.
    Negative deltas (sale before acquisition — should never happen in
    well-formed inputs) are clamped to 0 and treated as SHORT so the
    function stays total.

    > 365 days → "LONG", else "SHORT" (per IRS Pub. 550).
    """
    delta = (sale_date - acquisition_date).days
    if delta < 0:
        delta = 0
    term = "LONG" if delta > _LONG_TERM_THRESHOLD_DAYS else "SHORT"
    return term, delta


def _to_decimal(v: Any) -> Decimal:
    """Coerce numeric input to Decimal without losing precision.

    Accepts Decimal / int / str. Floats are intentionally rejected
    (tax math must round-trip exactly); callers should send Decimal.
    """
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, str):
        return Decimal(v)
    if v is None:
        return Decimal("0")
    raise TypeError(
        f"tax_report expects Decimal/int/str numerics, got {type(v).__name__}"
    )


def _allocate(
    total_amount: Decimal, matched_qty: Decimal, base_qty: Decimal
) -> Decimal:
    """Allocate `total_amount` proportionally to `matched_qty / base_qty`.

    Returns 0 when `base_qty` is 0 (defensive — should never happen
    given upstream invariants but keeps the function total). Decimal
    division preserves precision; the caller chooses any further
    quantization.
    """
    if base_qty <= Decimal("0"):
        return Decimal("0")
    return total_amount * matched_qty / base_qty


def compute_matched_pairs(
    buy_lots_history: list[dict],
    sell_trades: list[dict],
) -> list[TaxLotMatch]:
    """FIFO-match each SELL to the oldest available BUYs.

    Inputs (decoupled from ORM — caller projects rows to dicts):

    Each `buy_lots_history` item:
        {trade_id, symbol, market, acquisition_date, qty,
         cost_per_unit, total_fee}
        - `qty` is the BUY's original quantity (NOT remaining).
        - `cost_per_unit` is the price paid (pre-fee). Fee allocation
          happens here so the caller does not double-count.
        - `total_fee` is the BUY-side fee charged on the original qty.

    Each `sell_trades` item:
        {trade_id, symbol, market, sale_date, qty, price_per_unit,
         total_fee, total_tax}
        - `qty` is the SELL's total quantity.
        - `price_per_unit` is the gross sell price.
        - `total_fee` + `total_tax` reduce proceeds (US: tax usually
          0 but kept for non-US markets feeding the same pipeline).

    Algorithm:
        1. Group BUYs by (symbol, market). Sort each group by
           (acquisition_date ASC, trade_id ASC) → FIFO queue.
        2. Group SELLs by (symbol, market). Sort each group by
           (sale_date ASC, trade_id ASC) → chronological consumption.
        3. For each SELL, drain the BUY queue from the head until
           the SELL's qty is satisfied. Each touched BUY emits one
           `TaxLotMatch`. Partial consumption updates the BUY's
           remaining qty in-place on the queue.
        4. If the BUY queue runs dry before the SELL is satisfied,
           raise `ValueError` — input log is inconsistent. The service
           layer should never feed inconsistent data because the
           trade-log replay guarantees BUY total >= SELL total per
           (symbol, market) tuple.

    Returns:
        Flat list of `TaxLotMatch`, ordered by (sale_date ASC,
        sell_trade_id ASC, acquisition_date ASC).

    Raises:
        ValueError: when a SELL exceeds the available BUY qty for its
            (symbol, market) — programmer error upstream.
    """
    # ── Group BUYs into FIFO queues keyed by (symbol, market) ──────────
    queues: dict[tuple[str, str], deque[dict]] = {}
    for raw in buy_lots_history:
        key = (raw["symbol"], raw["market"])
        queues.setdefault(key, deque())
        # Shallow copy so we can mutate `remaining_qty` without
        # touching the caller's list.
        original_qty = _to_decimal(raw["qty"])
        queues[key].append(
            {
                "trade_id": raw["trade_id"],
                "symbol": raw["symbol"],
                "market": raw["market"],
                "acquisition_date": raw["acquisition_date"],
                "original_qty": original_qty,
                "remaining_qty": original_qty,
                "cost_per_unit": _to_decimal(raw["cost_per_unit"]),
                "total_fee": _to_decimal(raw.get("total_fee", Decimal("0"))),
            }
        )
    # Sort each queue chronologically — FIFO consumption order.
    for key in queues:
        ordered = sorted(
            queues[key],
            key=lambda b: (b["acquisition_date"], b["trade_id"]),
        )
        queues[key] = deque(ordered)

    # ── Sort SELLs chronologically (stable across symbols) ─────────────
    sorted_sells = sorted(
        sell_trades,
        key=lambda s: (s["sale_date"], s["trade_id"]),
    )

    matches: list[TaxLotMatch] = []
    for sell in sorted_sells:
        symbol = sell["symbol"]
        market = sell["market"]
        sale_date = sell["sale_date"]
        sell_total_qty = _to_decimal(sell["qty"])
        sell_price = _to_decimal(sell["price_per_unit"])
        sell_fee = _to_decimal(sell.get("total_fee", Decimal("0")))
        sell_tax = _to_decimal(sell.get("total_tax", Decimal("0")))
        sell_total_costs = sell_fee + sell_tax

        key = (symbol, market)
        queue = queues.get(key)
        remaining_to_consume = sell_total_qty

        while remaining_to_consume > Decimal("0"):
            if queue is None or not queue:
                raise ValueError(
                    f"insufficient BUY history to match SELL trade_id="
                    f"{sell['trade_id']} {symbol}/{market}: "
                    f"{remaining_to_consume} shares unmatched"
                )
            head = queue[0]
            consume = (
                head["remaining_qty"]
                if head["remaining_qty"] <= remaining_to_consume
                else remaining_to_consume
            )

            # Cost basis: gross price portion + allocated fraction of BUY fee.
            cost_basis = (
                head["cost_per_unit"] * consume
                + _allocate(head["total_fee"], consume, head["original_qty"])
            )
            # Proceeds: gross sell portion - allocated fraction of SELL fee+tax.
            proceeds = (
                sell_price * consume
                - _allocate(sell_total_costs, consume, sell_total_qty)
            )
            term, days = classify_holding_period(
                head["acquisition_date"], sale_date
            )
            matches.append(
                TaxLotMatch(
                    symbol=symbol,
                    market=market,
                    quantity=consume,
                    acquisition_date=head["acquisition_date"],
                    sale_date=sale_date,
                    cost_basis=cost_basis,
                    proceeds=proceeds,
                    gain_loss=proceeds - cost_basis,
                    holding_period_days=days,
                    term=term,
                    is_wash_sale=False,
                )
            )
            head["remaining_qty"] -= consume
            remaining_to_consume -= consume
            if head["remaining_qty"] <= Decimal("0"):
                queue.popleft()

    return matches


def summarize_by_year(
    matches: list[TaxLotMatch],
) -> dict[int, TaxYearSummary]:
    """Group matches by `sale_date.year`; compute per-year totals.

    Gains are summed separately from losses so the Schedule D-style
    "gain" / "loss" columns are populated (IRS expects both, even
    when one is zero). `*_net` = gain + loss (loss is negative).

    Empty input → empty dict (no allocation; callers may treat as
    "user has no taxable activity").
    """
    by_year: dict[int, list[TaxLotMatch]] = {}
    for m in matches:
        by_year.setdefault(m.sale_date.year, []).append(m)

    summaries: dict[int, TaxYearSummary] = {}
    for year, ms in by_year.items():
        st_gain = Decimal("0")
        st_loss = Decimal("0")
        lt_gain = Decimal("0")
        lt_loss = Decimal("0")
        for m in ms:
            if m.term == "SHORT":
                if m.gain_loss >= Decimal("0"):
                    st_gain += m.gain_loss
                else:
                    st_loss += m.gain_loss
            else:  # LONG
                if m.gain_loss >= Decimal("0"):
                    lt_gain += m.gain_loss
                else:
                    lt_loss += m.gain_loss
        st_net = st_gain + st_loss
        lt_net = lt_gain + lt_loss
        summaries[year] = TaxYearSummary(
            tax_year=year,
            short_term_gain=st_gain,
            short_term_loss=st_loss,
            short_term_net=st_net,
            long_term_gain=lt_gain,
            long_term_loss=lt_loss,
            long_term_net=lt_net,
            total_net=st_net + lt_net,
            total_matches=len(ms),
        )
    return summaries
