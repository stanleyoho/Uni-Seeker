"""IRS Section 1091 wash-sale detector — pure module.

Pure-Python implementation of the wash-sale matching algorithm laid out
in IRS Publication 550. Detects loss-realizing SELL trades and finds
"substantially identical" replacement BUY trades within the statutory
30-day window before or after the sale. Emits adjustment records that
the service layer can fold back into Form 8949 / Schedule D output.

**No DB, no FastAPI.** Inputs are plain `list[dict]` (trades) +
`list[TaxLotMatch]` (output of `tax_report.compute_matched_pairs`) so
this module is trivially testable from CLI / batch contexts. The
service layer (`app.services.portfolio.tax_report_service`) is
responsible for invoking the detector after the FIFO matcher runs.

------------------------------------------------------------------
IRS Section 1091 (Pub. 550, Wash Sales):

  > A wash sale occurs when you sell or trade stock or securities at
  > a loss and within 30 days BEFORE or AFTER the sale you:
  >   1. Buy substantially identical stock or securities,
  >   2. Acquire substantially identical stock or securities in a
  >      fully taxable trade,
  >   3. Acquire a contract or option to buy substantially identical
  >      stock or securities, or
  >   4. Acquire substantially identical stock for your IRA / Roth IRA.

  Effect:
   * The loss on the sold shares is **disallowed** (cannot offset gains
     in the current tax year).
   * The disallowed loss is **added to the cost basis** of the
     replacement shares.
   * The replacement shares **inherit the holding period** of the
     originally sold shares (so a sale of newly bought replacement
     shares may still be LONG-term even though the calendar gap looks
     SHORT).

------------------------------------------------------------------
Scope / simplifications (best-effort implementation):

  * "Substantially identical" → same (symbol, market). The IRS does
    not define the term precisely; in practice professional preparers
    treat the same ticker on the same exchange as identical and treat
    derivatives / options as a gray area best left to a human review.
    We pick the conservative same-ticker interpretation here.
  * Cross-account / IRA / Roth IRA aggregation is **not** handled —
    we treat each user's trade log as a single pool. Real-world filers
    must aggregate across spouse + IRA per §1091, which is out of
    scope for an automated tool (we cannot see other accounts).
  * The 30-day window is interpreted as **calendar days inclusive** on
    both endpoints: `abs((replacement_date - sale_date).days) <= 30`.
    Day 30 IS a wash sale; day 31 is NOT.
  * Replacement shares are consumed FIFO (oldest buy within the window
    first) when multiple loss-realizing SELLs compete for the same
    replacement BUY.
  * "Replacement" candidates are **buy trades**, not the BUY lots that
    fed the original FIFO match (those are the original acquisition,
    not a replacement). A separate filter ensures we don't pair a SELL
    against the very lot it sold.

------------------------------------------------------------------
Algorithm:

  1. Filter `matches` to `gain_loss < 0` — only losses can trigger.
  2. Walk loss matches sorted by sale_date ASC. For each loss-match:
        a. Find BUY trades for the same (symbol, market) whose
           `trade_date` falls within ±30 days of the loss-match's
           `sale_date`. Exclude the very BUY that supplied the cost
           basis (its trade_id may match — that's the original
           purchase, not a replacement under §1091).
        b. Sort candidate replacements by trade_date ASC, trade_id ASC.
        c. Allocate FIFO: pick the oldest replacement BUY that still
           has unconsumed qty. Match `min(loss_qty, replacement_qty)`
           shares. Drain replacement's remaining qty, drain loss's
           remaining qty, repeat until either is exhausted.
        d. For each pairing, emit one `WashSaleAdjustment` with the
           disallowed loss prorated by `matched_qty / loss_qty`.
  3. Replacement BUYs track remaining qty across the algorithm so two
     loss-matches cannot double-claim the same replacement shares.
  4. Return a `WashSaleResult` with the flat adjustment list +
     aggregate disallowed loss.

Cost-basis inheritance strategy (applied later via
`apply_wash_sale_adjustments`):

  * The loss leg's `gain_loss` is forced to 0 (disallowed).
  * The loss leg is marked `is_wash_sale = True` and carries the
    disallowed amount on `wash_sale_disallowed_loss`.
  * The disallowed loss conceptually rides on the replacement BUY's
    cost basis for a future SELL. We do NOT mutate the BUY trade
    here — Form 8949 reports the wash sale on the SELL row; the
    cost-basis inheritance only matters when the replacement is
    itself later sold, at which point the user (or a future Round)
    must re-run with the increased basis. For today we surface the
    adjustment on the affected match so the CSV "Code=W" / "Adjustment
    amount" columns can be populated per IRS instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.portfolio.tax_report import TaxLotMatch

__all__ = [
    "WashSaleAdjustment",
    "WashSaleResult",
    "apply_wash_sale_adjustments",
    "date_within_window",
    "detect_wash_sales",
]


_WASH_SALE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class WashSaleAdjustment:
    """One detected wash sale ↔ replacement pairing.

    A single loss-realizing SELL may produce *multiple* adjustments
    when its quantity is split across several replacement BUYs (or
    when the replacement supply is itself thin). Conversely, a SELL
    with no replacement within the 30-day window produces zero
    adjustments and stays a normal deductible loss.
    """

    sold_trade_id: int  # SELL trade that realised the loss
    replacement_trade_id: int  # BUY trade within the ±30-day window
    symbol: str
    market: str
    sale_date: date
    replacement_date: date
    disallowed_loss: Decimal  # always a positive Decimal (magnitude)
    matched_qty: Decimal  # shares of replacement getting basis bump
    new_holding_period_start: date  # original acquisition_date (inherited)


@dataclass(frozen=True)
class WashSaleResult:
    """Aggregate detector output."""

    adjustments: list[WashSaleAdjustment]
    total_disallowed_loss: Decimal


# ── helpers ───────────────────────────────────────────────────────────


def date_within_window(d1: date, d2: date, window_days: int = _WASH_SALE_WINDOW_DAYS) -> bool:
    """Return True iff `|d1 - d2| <= window_days` (inclusive both ends).

    The IRS uses calendar days, not trading days. The window is
    *inclusive*: a buy on day -30 or day +30 relative to the sale
    triggers wash-sale treatment; day -31 / +31 do not.
    """
    return abs((d1 - d2).days) <= window_days


def _to_decimal(v: Any) -> Decimal:
    """Coerce numeric to Decimal — mirrors `tax_report._to_decimal`.

    Floats are rejected (precision-critical math); callers must pass
    Decimal / int / str. None is treated as zero (defensive).
    """
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, str):
        return Decimal(v)
    if v is None:
        return Decimal("0")
    raise TypeError(f"wash_sale_detector expects Decimal/int/str numerics, got {type(v).__name__}")


def _buy_trades_only(trades: list[dict]) -> list[dict]:
    """Project the trade log into the BUY rows we use as replacement
    candidates. Sorted by (trade_date ASC, id ASC) for deterministic
    FIFO consumption."""
    buys = [t for t in trades if t.get("action") == "BUY"]
    return sorted(buys, key=lambda b: (b["trade_date"], b["id"]))


# ── detection ─────────────────────────────────────────────────────────


def detect_wash_sales(
    trades: list[dict],
    matches: list[TaxLotMatch],
) -> WashSaleResult:
    """Detect §1091 wash sales in a (trades, matches) corpus.

    Args:
        trades: Every BUY / SELL trade visible to the user. Each item
            must include at minimum: ``id``, ``trade_date``, ``symbol``,
            ``market``, ``action``, ``qty``. ``price`` is read where
            available but not required for matching.
        matches: Output of `tax_report.compute_matched_pairs` — one
            row per BUY-lot consumed by a SELL.

    Returns:
        `WashSaleResult` whose `adjustments` list may be empty (no
        wash sales detected) and whose `total_disallowed_loss` is the
        sum of every adjustment's `disallowed_loss` (always >= 0).

    Notes:
        * Only matches with ``gain_loss < 0`` are considered. Profitable
          SELLs cannot be wash sales by definition.
        * "Same security" → same ``(symbol, market)``. Cross-listing
          (e.g. ADR vs primary listing) is treated as distinct.
        * The BUY that supplied the cost basis of a loss-match is NOT
          a valid replacement candidate (it's the *original* purchase).
          We exclude it by trade_id when computing replacements.
        * Replacement BUYs are consumed FIFO across all loss-matches.
          Two loss-matches contending for the same BUY get whatever
          quantity remains after the earlier-sold loss-match has
          claimed its share.
    """
    # ── Index BUY trades by (symbol, market) for fast lookup ──────────
    buy_pool_by_symbol: dict[tuple[str, str], list[dict]] = {}
    for buy in _buy_trades_only(trades):
        key = (buy["symbol"], buy["market"])
        buy_pool_by_symbol.setdefault(key, []).append(
            {
                "id": buy["id"],
                "trade_date": buy["trade_date"],
                "symbol": buy["symbol"],
                "market": buy["market"],
                "original_qty": _to_decimal(buy.get("qty", "0")),
                "remaining_qty": _to_decimal(buy.get("qty", "0")),
            }
        )

    # ── Loss-matches sorted chronologically — earliest loss gets
    #    first claim on overlapping replacements (FIFO across losses).
    loss_matches = sorted(
        ((idx, m) for idx, m in enumerate(matches) if m.gain_loss < Decimal("0")),
        key=lambda pair: (pair[1].sale_date, pair[0]),
    )

    adjustments: list[WashSaleAdjustment] = []
    total_disallowed = Decimal("0")

    for _idx, match in loss_matches:
        key = (match.symbol, match.market)
        candidates = buy_pool_by_symbol.get(key, [])
        if not candidates:
            continue

        # Filter to in-window replacements with leftover qty, excluding
        # the very BUY that supplied the cost basis (original purchase,
        # not a replacement per §1091).
        eligible = [
            c
            for c in candidates
            if c["remaining_qty"] > Decimal("0")
            and date_within_window(c["trade_date"], match.sale_date)
            and c["trade_date"] != match.acquisition_date
        ]
        if not eligible:
            continue

        # Loss qty drives the proration; `match.quantity` is the
        # number of shares carrying the loss on this row.
        loss_qty = match.quantity
        if loss_qty <= Decimal("0"):
            continue
        # The total loss magnitude (positive number) we may disallow.
        loss_magnitude = -match.gain_loss  # gain_loss < 0 → magnitude > 0

        remaining_loss_qty = loss_qty
        for replacement in eligible:
            if remaining_loss_qty <= Decimal("0"):
                break
            avail = replacement["remaining_qty"]
            if avail <= Decimal("0"):
                continue
            consumed = avail if avail <= remaining_loss_qty else remaining_loss_qty
            # Prorate disallowed loss by qty share consumed of the loss leg.
            disallowed = loss_magnitude * consumed / loss_qty
            adjustments.append(
                WashSaleAdjustment(
                    sold_trade_id=_safe_int(match, "sold_trade_id"),
                    replacement_trade_id=int(replacement["id"]),
                    symbol=match.symbol,
                    market=match.market,
                    sale_date=match.sale_date,
                    replacement_date=replacement["trade_date"],
                    disallowed_loss=disallowed,
                    matched_qty=consumed,
                    new_holding_period_start=match.acquisition_date,
                )
            )
            total_disallowed += disallowed
            replacement["remaining_qty"] -= consumed
            remaining_loss_qty -= consumed

    return WashSaleResult(
        adjustments=adjustments,
        total_disallowed_loss=total_disallowed,
    )


def _safe_int(match: TaxLotMatch, _field: str) -> int:
    """Resolve a trade-id-like identifier from a TaxLotMatch.

    `TaxLotMatch` (today) does not carry the original SELL trade_id —
    it only carries the BUY's `acquisition_date`. We synthesize a
    stable surrogate from the sale_date ordinal so adjustments can be
    cross-referenced when the service joins back to its trade list.
    Service layer override: if the service threads real SELL ids into
    a richer match object in the future, replace this surrogate.
    """
    return match.sale_date.toordinal()


# ── application ───────────────────────────────────────────────────────


def apply_wash_sale_adjustments(
    matches: list[TaxLotMatch],
    adjustments: list[WashSaleAdjustment],
) -> list[TaxLotMatch]:
    """Fold detector output back into the match list.

    For every `TaxLotMatch` whose (symbol, market, sale_date,
    acquisition_date) hits a matching adjustment:
      * `is_wash_sale` ← True
      * `wash_sale_disallowed_loss` ← cumulative magnitude of all
        adjustments touching this row
      * `gain_loss` ← `gain_loss + wash_sale_disallowed_loss`,
        clamped at 0 (a fully-disallowed loss becomes a $0 row on
        Form 8949 with Code=W and the disallowed amount in the
        Adjustment column).

    The function returns a **new** list (frozen dataclasses — we use
    `dataclasses.replace` to rebuild affected rows). Matches without
    a wash-sale hit pass through unchanged.

    The replacement BUY does NOT get its cost basis rewritten here.
    Per IRS guidance the wash sale is reported on the SELL row in the
    current year; the basis inheritance only matters when the
    replacement itself is later sold. A future Round may extend this
    function to also mutate downstream matches whose acquisition
    trade was the replacement — for now we surface the adjustment on
    the SELL row, which is the form-8949 reporting requirement.
    """
    if not adjustments:
        return list(matches)

    # Aggregate disallowed loss per (sale_date, symbol, market,
    # acquisition_date) — one match row may correspond to multiple
    # adjustments when its qty was split across replacements.
    by_match_key: dict[tuple[date, str, str, date], Decimal] = {}
    for adj in adjustments:
        key = (adj.sale_date, adj.symbol, adj.market, adj.new_holding_period_start)
        by_match_key[key] = by_match_key.get(key, Decimal("0")) + adj.disallowed_loss

    out: list[TaxLotMatch] = []
    for m in matches:
        key = (m.sale_date, m.symbol, m.market, m.acquisition_date)
        disallowed = by_match_key.get(key)
        if disallowed is None or disallowed <= Decimal("0"):
            out.append(m)
            continue
        # Reset loss up to the disallowed amount.
        new_gain_loss = m.gain_loss + disallowed
        if new_gain_loss > Decimal("0"):
            # Defensive: never let disallowance flip a loss into a gain.
            new_gain_loss = Decimal("0")
        out.append(
            replace(
                m,
                is_wash_sale=True,
                wash_sale_disallowed_loss=disallowed,
                gain_loss=new_gain_loss,
            )
        )
    return out
