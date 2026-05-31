"""Candlestick pattern detection (TA-Lib backed).

Exposes a small façade over TA-Lib's ``CDL*`` functions so the scanner
endpoint and any future caller can ask:

    "which of the six tracked patterns are firing on the latest bar of
    this OHLC series?"

We intentionally limit the public surface to the **six high-signal
patterns** Stanley prioritized (per the integration spec), rather than
exposing the full TA-Lib catalog of ~60+ pattern functions:

    * CDLDOJI         — single-bar indecision (open ≈ close)
    * CDLENGULFING    — two-bar reversal (today's body engulfs yesterday's)
    * CDLHAMMER       — single-bar bullish reversal (long lower wick)
    * CDLMORNINGSTAR  — three-bar bullish reversal
    * CDLEVENINGSTAR  — three-bar bearish reversal
    * CDLSHOOTINGSTAR — single-bar bearish reversal (long upper wick)

TA-Lib pattern functions return per-bar ``int`` values:
    +100 = bullish pattern detected at this bar
    -100 = bearish pattern detected at this bar
       0 = no pattern

The directionality matters for ENGULFING / HAMMER / SHOOTINGSTAR (where
the same shape produces ±100 depending on the bar's color), but for
DOJI the function only ever emits ``+100`` because the pattern is
direction-neutral.

The public function ``detect_patterns`` returns a ``list[str]`` of the
pattern names firing on the **latest bar** — that is the shape the
``/scanner/scan`` response expects (one short list per stock).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.indicators.talib_wrappers import PATTERN_FUNCS, pattern

# Patterns we expose. Keep this tuple stable — the scanner response
# documents it and the OpenAPI schema enumerates from it.
SUPPORTED_PATTERNS: tuple[str, ...] = (
    "CDLDOJI",
    "CDLENGULFING",
    "CDLHAMMER",
    "CDLMORNINGSTAR",
    "CDLEVENINGSTAR",
    "CDLSHOOTINGSTAR",
)


@dataclass(frozen=True)
class PatternHit:
    """A single pattern detection on the latest bar.

    Attributes:
        name: TA-Lib pattern function name (e.g. ``"CDLDOJI"``).
        direction: ``+1`` bullish, ``-1`` bearish, ``0`` neutral
            (direction-agnostic patterns like DOJI emit ``0``).
    """

    name: str
    direction: int


def detect_patterns(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    patterns: tuple[str, ...] = SUPPORTED_PATTERNS,
) -> list[PatternHit]:
    """Run every requested TA-Lib candlestick pattern and return hits
    on the **latest bar**.

    Parameters
    ----------
    opens, highs, lows, closes:
        OHLC series, chronologically ordered (oldest first). All four
        lists must be the same length; if any are mismatched or empty,
        this function returns an empty list (no spurious False signals).
    patterns:
        Tuple of pattern names to check. Defaults to all six supported
        patterns. Caller can pass a subset to limit work.

    Returns
    -------
    list[PatternHit]
        One entry per pattern that fired on the latest bar. Empty list
        when no patterns fired or input is unusable.
    """
    n = len(closes)
    # Guard: TA-Lib's MORNINGSTAR/EVENINGSTAR need at least 3 bars,
    # ENGULFING needs 2, others need 1. Use 3 as a conservative floor
    # rather than per-pattern minimums — the cost of one extra empty
    # call is negligible (~µs per pattern on a 60-bar series).
    if n < 3 or len(opens) != n or len(highs) != n or len(lows) != n:
        return []

    hits: list[PatternHit] = []
    for name in patterns:
        if name not in PATTERN_FUNCS:
            # Skip unknown names rather than raise — the public surface
            # of this module is stable, but callers might pass a future
            # pattern name we haven't shipped yet.
            continue
        series = pattern(name, opens, highs, lows, closes)
        latest = series[-1] if series else None
        if latest is None or latest == 0:
            continue
        # Normalize to ±1/0 for the direction (TA-Lib returns ±100).
        direction = 1 if latest > 0 else (-1 if latest < 0 else 0)
        hits.append(PatternHit(name=name, direction=direction))
    return hits


def pattern_names(hits: list[PatternHit]) -> list[str]:
    """Convenience: list[PatternHit] → list[str] for the JSON response.

    The scanner endpoint serializes results as a flat list of pattern
    names; this strips the direction metadata. (Direction is preserved
    inside ``PatternHit`` for any consumer that wants the full picture
    later, e.g. a per-stock dashboard.)
    """
    return [h.name for h in hits]
