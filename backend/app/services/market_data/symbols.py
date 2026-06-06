"""Symbol classification for market-data routing.

The registry uses these helpers to decide *which* provider owns a given
symbol. The rules mirror the suffix conventions already produced by the
existing providers:

* ``twse.py`` emits ``f"{code}.TW"`` (e.g. ``"2330.TW"``)
* ``tpex.py`` emits ``f"{code}.TWO"`` (e.g. ``"6488.TWO"``)
* ``yfinance_provider.py`` is called with raw US tickers (e.g. ``"AAPL"``)
* FinMind is called with the *bare* Taiwan ``stock_id`` (e.g. ``"2330"``)

Classification is a pure string function — no I/O, no network — so it is
cheap to call per-request and trivially testable.
"""

from __future__ import annotations

import enum


class MarketClass(enum.StrEnum):
    """Coarse market bucket a symbol belongs to.

    Intentionally coarser than :class:`app.models.enums.Market`: a bare
    Taiwan code (``"2330"``) cannot be split into TWSE vs TPEX from the
    string alone, so it maps to :attr:`TW` and is served by whichever TW
    provider is registered for that bucket (FinMind, which accepts the
    bare ``stock_id``).
    """

    TW_TWSE = "TW_TWSE"
    TW_TPEX = "TW_TPEX"
    TW = "TW"
    US = "US"


def classify_symbol(symbol: str) -> MarketClass:
    """Return the :class:`MarketClass` for ``symbol`` based on its suffix.

    Rules (checked in order):

    * ``*.TWO``           -> :attr:`MarketClass.TW_TPEX`
    * ``*.TW``            -> :attr:`MarketClass.TW_TWSE`
    * all-digit code      -> :attr:`MarketClass.TW` (bare Taiwan stock_id)
    * everything else     -> :attr:`MarketClass.US`

    Parameters
    ----------
    symbol : str
        A ticker such as ``"2330.TW"``, ``"6488.TWO"``, ``"2330"`` or
        ``"AAPL"``. Case-insensitive on the suffix.
    """
    s = symbol.strip().upper()
    if s.endswith(".TWO"):
        return MarketClass.TW_TPEX
    if s.endswith(".TW"):
        return MarketClass.TW_TWSE
    # Bare Taiwan codes are numeric (optionally with a letter suffix like
    # "2330A" for special-condition issues). Treat purely-digit codes, and
    # digit-prefixed codes, as Taiwan; anything starting with a letter is US.
    if s and s[0].isdigit():
        return MarketClass.TW
    return MarketClass.US


def to_bare_tw_code(symbol: str) -> str:
    """Strip the ``.TW`` / ``.TWO`` suffix to get the bare Taiwan code.

    FinMind's API keys on the bare ``stock_id`` (``"2330"``), whereas the
    rest of the system uses suffixed symbols (``"2330.TW"``). This is the
    inverse of the ``f"{code}.TW"`` formatting done in the TW providers.
    """
    s = symbol.strip()
    for suffix in (".TWO", ".TW"):
        if s.upper().endswith(suffix):
            return s[: -len(suffix)]
    return s
