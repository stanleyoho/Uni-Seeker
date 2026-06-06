"""Pure indicator computation for the live watchlist panel — A2 (scoped v1).

This module owns NO indicator math of its own. It assembles a small
panel-friendly snapshot from:

  * the latest values of indicators computed by the existing TA-Lib wrappers
    (``app.modules.indicators.talib_wrappers``) — RSI(14) and two SMAs, and
  * an optional live price (supplied by the caller from the portfolio
    live-price fetcher).

Keeping this layer pure (``list[float] -> snapshot``) means it is trivially
unit-testable and import-linter clean: it never touches the DB, the network,
or the HTTP layer. The endpoint does the I/O (DB read + price fetch) and
hands the numbers here.

Why ``Decimal`` on the way out: the API serialises money/indicator fields as
Decimal-as-string (project convention). We build ``Decimal`` from
``str(float)`` to avoid binary-float artefacts, mirroring how the live-price
fetcher coerces yfinance floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.indicators.talib_wrappers import rsi as talib_rsi
from app.modules.indicators.talib_wrappers import sma as talib_sma

# Default windows for the panel. Short/long SMA pair gives the classic
# golden/death cross; RSI(14) is the canonical default. Kept module-level so
# the endpoint and tests reference the same constants.
DEFAULT_RSI_PERIOD = 14
DEFAULT_MA_SHORT = 5
DEFAULT_MA_LONG = 20

# MA-cross state strings — small closed vocabulary the frontend switches on.
CROSS_GOLDEN = "golden"  # short MA above long MA (bullish)
CROSS_DEATH = "death"  # short MA below long MA (bearish)
CROSS_FLAT = "flat"  # exactly equal (rare; included for completeness)


@dataclass(frozen=True)
class LiveIndicatorSnapshot:
    """Panel-ready snapshot for a single symbol.

    Every numeric field is ``Decimal | None``; the HTTP layer stringifies
    them. ``None`` means "not available" (insufficient history / no price),
    which the frontend renders as an em-dash.
    """

    last_price: Decimal | None
    prev_close: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    rsi: Decimal | None
    ma_short: Decimal | None
    ma_long: Decimal | None
    ma_cross: str | None
    pct_from_ma_long: Decimal | None


def _latest(values: list[float | None]) -> float | None:
    """Return the last non-``None`` value of an indicator series, else None.

    TA-Lib wrappers pad the warmup window with ``None``; the panel only cares
    about the most recent *computed* value, so we scan from the tail.
    """
    for v in reversed(values):
        if v is not None:
            return v
    return None


def _dec(value: float | None) -> Decimal | None:
    """Coerce a float to ``Decimal`` via ``str`` (no binary-float artefacts)."""
    if value is None:
        return None
    return Decimal(str(value))


def compute_live_indicators(
    closes: list[float],
    *,
    last_price: Decimal | None = None,
    prev_close: Decimal | None = None,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    ma_short: int = DEFAULT_MA_SHORT,
    ma_long: int = DEFAULT_MA_LONG,
) -> LiveIndicatorSnapshot:
    """Assemble a :class:`LiveIndicatorSnapshot` from daily-close history.

    Args:
        closes: Ascending daily-close prices (oldest → newest). May be empty.
        last_price: Current/live price from the price feed (``None`` if no
            feed). When omitted, ``change``/``change_percent`` and
            ``pct_from_ma_long`` are computed against the latest close instead,
            so the panel still shows MA-relative context from history alone.
        prev_close: Previous close from the price feed; used for change calc.
            Falls back to the second-to-last historical close when ``None``.
        rsi_period: RSI lookback (default 14).
        ma_short / ma_long: SMA windows for the cross (default 5 / 20).

    Returns:
        A snapshot with ``Decimal | None`` fields. All math is delegated to
        the shared TA-Lib wrappers — this function only picks latest values
        and derives ratios.
    """
    # Indicator series (warmup padded with None) from the shared wrappers.
    rsi_latest = _latest(talib_rsi(closes, period=rsi_period)) if closes else None
    ma_short_latest = _latest(talib_sma(closes, period=ma_short)) if closes else None
    ma_long_latest = _latest(talib_sma(closes, period=ma_long)) if closes else None

    # Reference price for ratio math: prefer the live price, else latest close.
    ref_price = last_price if last_price is not None else _dec(closes[-1] if closes else None)

    # prev_close fallback: 2nd-to-last historical close when feed omits it.
    effective_prev = prev_close
    if effective_prev is None and len(closes) >= 2:
        effective_prev = _dec(closes[-2])

    change: Decimal | None = None
    change_percent: Decimal | None = None
    if ref_price is not None and effective_prev is not None:
        change = ref_price - effective_prev
        if effective_prev != 0:
            change_percent = (change / effective_prev) * Decimal("100")

    # MA cross state.
    ma_cross: str | None = None
    if ma_short_latest is not None and ma_long_latest is not None:
        if ma_short_latest > ma_long_latest:
            ma_cross = CROSS_GOLDEN
        elif ma_short_latest < ma_long_latest:
            ma_cross = CROSS_DEATH
        else:
            ma_cross = CROSS_FLAT

    # Percent distance of the reference price from the long MA.
    pct_from_ma_long: Decimal | None = None
    ma_long_dec = _dec(ma_long_latest)
    if ref_price is not None and ma_long_dec is not None and ma_long_dec != 0:
        pct_from_ma_long = ((ref_price - ma_long_dec) / ma_long_dec) * Decimal("100")

    return LiveIndicatorSnapshot(
        last_price=ref_price,
        prev_close=effective_prev,
        change=change,
        change_percent=change_percent,
        rsi=_dec(rsi_latest),
        ma_short=_dec(ma_short_latest),
        ma_long=ma_long_dec,
        ma_cross=ma_cross,
        pct_from_ma_long=pct_from_ma_long,
    )
