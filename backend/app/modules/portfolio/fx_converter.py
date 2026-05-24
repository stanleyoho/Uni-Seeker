"""Pure FX conversion math — Phase 4+ FX support.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11
      ("FX support" extensibility).

**No network, no DB, no float.** Mirrors the design of
`app/modules/portfolio/pnl.py`: this module is the single source of truth
for currency conversion arithmetic so service / API layers never duplicate
the multiplications.

Conversion contract:
    `quote_amount = base_amount * rate`
where `rate` comes from FxService / FxFetcher (`FxQuote.rate`). Callers
who already have a `rate_to_base` dict (quote_ccy → rate) use
`convert_to_base` to roll a multi-currency map into one base currency.

Edge-case contract:
  - `amount is None`             → returns None (pass-through)
  - `rate is None`               → raises ValueError (programmer error;
                                    caller should not pass None)
  - empty amounts dict           → Decimal("0")
  - missing rate for a currency  → FxRateMissing (KeyError subclass)
  - amount currency == base      → no rate lookup needed, added as-is
"""
from __future__ import annotations

from decimal import Decimal

__all__ = [
    "FxRateMissing",
    "convert",
    "convert_to_base",
    "convert_dict",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")


class FxRateMissing(KeyError):
    """Raised when no rate is available for one of the supplied currencies.

    Inherits from KeyError so callers that already handle dict.get-style
    misses can catch with `except KeyError` if they want generic handling,
    while still being able to special-case via `isinstance(exc, FxRateMissing)`.
    """

    def __init__(self, currency: str, base: str) -> None:
        super().__init__(currency)
        self.currency = currency
        self.base = base

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"no FX rate available for {self.currency} → {self.base}"


def convert(amount: Decimal | None, rate: Decimal) -> Decimal | None:
    """Apply rate; preserves None pass-through.

    Args:
        amount: Source amount in base currency; None propagates.
        rate: FX multiplier (`quote = base * rate`). Must not be None.

    Returns:
        `amount * rate` as Decimal, or None when input is None.

    Raises:
        ValueError: when `rate` is None (programmer error — callers must
                    resolve the rate before calling this function).
    """
    if rate is None:
        raise ValueError("convert(): rate must not be None")
    if amount is None:
        return None
    return amount * rate


def convert_to_base(
    amounts_by_currency: dict[str, Decimal],
    rates_to_base: dict[str, Decimal],
    base_currency: str,
) -> Decimal:
    """Sum all amounts converted to `base_currency`.

    Args:
        amounts_by_currency: e.g. ``{"USD": Decimal("100"), "JPY": Decimal("5000")}``.
        rates_to_base: mapping from source currency to base-multiplier such
            that ``base_amount = source_amount * rate``. The base currency
            itself need not be present (it short-circuits to 1.0).
        base_currency: ISO 4217 code (e.g. ``"TWD"``).

    Returns:
        Total in `base_currency` as Decimal.

    Raises:
        FxRateMissing: when a non-base currency in `amounts_by_currency`
            has no entry in `rates_to_base`.

    Edge cases:
        - empty `amounts_by_currency` → Decimal("0")
        - amount currency == base    → contributes amount * 1
        - rate present but == 0      → contributes 0 (no special-case)
    """
    base = base_currency.upper()
    if not amounts_by_currency:
        return _ZERO

    total = _ZERO
    for ccy, amount in amounts_by_currency.items():
        ccy_u = ccy.upper()
        if amount is None:
            continue
        if ccy_u == base:
            total += amount
            continue
        rate = rates_to_base.get(ccy_u)
        if rate is None:
            raise FxRateMissing(currency=ccy_u, base=base)
        total += amount * rate
    return total


def convert_dict(
    amounts_by_currency: dict[str, Decimal],
    rates_to_base: dict[str, Decimal],
    base_currency: str,
) -> dict[str, Decimal]:
    """Like `convert_to_base` but returns the per-currency contribution dict
    *expressed in base*, NOT the running total.

    Useful for the "breakdown" payload the API returns alongside the
    aggregated total so the UI can render each currency's slice in the
    user's chosen base.

    Returns:
        ``{currency: amount_in_base}`` — same keys as `amounts_by_currency`,
        values converted to `base_currency`.

    Raises:
        FxRateMissing: same as `convert_to_base`.
    """
    base = base_currency.upper()
    out: dict[str, Decimal] = {}
    for ccy, amount in amounts_by_currency.items():
        ccy_u = ccy.upper()
        if amount is None:
            continue
        if ccy_u == base:
            out[ccy_u] = amount
            continue
        rate = rates_to_base.get(ccy_u)
        if rate is None:
            raise FxRateMissing(currency=ccy_u, base=base)
        out[ccy_u] = amount * rate
    return out
