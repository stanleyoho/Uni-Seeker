"""四大買賣點 (Best Four Buy/Sell Points) — pure computation.

Faithful reimplementation of twstock's ``BestFourPoint`` heuristic
(https://github.com/mlouielu/twstock — ``twstock/analytics.py``) on
Uni-Seeker's *own* daily OHLCV data, so the signals stay consistent with
every other scanner in the app instead of diverging from a self-fetched
twstock dataset.

We deliberately do NOT ``pip install twstock`` (poorly maintained, fetches
its own data). Instead this module reproduces the exact decision logic of
twstock's ``BestFourPoint`` class against ``list[float]`` series — the same
input shape every other indicator in this codebase consumes.

Algorithm — the eight points
============================
twstock works on chronological series (oldest first); ``[-1]`` is *today*,
``[-2]`` is the previous trading day. ``price`` == close, ``capacity`` ==
volume, ``open`` == open. Two moving averages of *close* drive points 3 & 4:
MA3 (three-day) and MA6 (six-day).

四大買點 (buy):
  1. 量大收紅      — volume rose vs prior day AND today closed up
                     (close[-1] > open[-1]).
  2. 量縮價不跌    — volume shrank vs prior day AND today's close held above
                     *yesterday's open* (close[-1] > open[-2]).
  3. 三日均價由下往上 — MA3 just turned up: the most-recent run of the MA3
                     series is a single up-step (``continuous(MA3) == 1``).
  4. 三日均價 > 六日均價 — MA3[-1] > MA6[-1] (short above mid = upward bias).

四大賣點 (sell): mirror images —
  1. 量大收黑      — volume rose AND today closed down (close[-1] < open[-1]).
  2. 量縮價跌      — volume shrank AND close[-1] < open[-2].
  3. 三日均價由上往下 — ``continuous(MA3) == -1``.
  4. 三日均價 < 六日均價 — MA3[-1] < MA6[-1].

The bias-pivot gate
===================
twstock does NOT emit raw buy/sell points directly. It gates them through a
*bias-ratio pivot* on the (MA3 − MA6) spread:

  - BUY points only count when ``mins_bias_ratio()`` is True — the spread
    has recently bottomed out below zero and is pivoting back up (a low
    base turning). This is twstock's way of saying "only call a buy when
    the short MA was below the mid MA and is now curling up", which filters
    out buy points fired in the middle of an established uptrend.
  - SELL points only count when ``plus_bias_ratio()`` is True — the spread
    recently topped out above zero and is pivoting down.

``ma_bias_ratio_pivot(sample_size=5)`` looks at the last 5 spread values and
finds the extreme (min for buy, max for sell). The pivot fires when:
  * the extreme is within the last 4 bars (``sample_size - idx < 4``), AND
  * the extreme is NOT today itself (``idx != sample_size - 1``), AND
  * for buy: ``max(sample) < 0`` (spread genuinely negative);
    for sell: ``max(sample) > 0`` (spread genuinely positive).

Verdict
=======
twstock returns a single boolean (buy>sell priority). We keep the richer
per-point breakdown AND add an explicit three-way verdict driven by the
NET count of *gated* points (the points that survive the bias gate):

  - 買進  (BUY)    when there are gated buy points and net ≥ +1
  - 賣出  (SELL)   when there are gated sell points and net ≤ -1
  - 觀望  (HOLD)   otherwise (no gated points, or buy/sell cancel out)

"net" = (#gated buy points) − (#gated sell points). Because the bias gate
is mutually-incompatible in practice (the spread can't have both recently
bottomed-below-zero and topped-above-zero in the same 5-bar window), a
symbol almost always has points on at most one side; the net rule degrades
gracefully if both ever appear.

Thresholds (all documented, all twstock-faithful)
=================================================
  MA_SHORT = 3, MA_MID = 6          — twstock's 3/6-day MAs.
  PIVOT_SAMPLE_SIZE = 5             — twstock's bias-pivot lookback window.
  PIVOT_RECENT_BARS = 4             — extreme must be within last 4 bars.
  MIN_BARS = 7                      — minimum series length: MA6 needs 6
                                      closes and the (MA3−MA6) spread + the
                                      5-bar pivot window + the volume[-2] /
                                      open[-2] look-back all need ≥ 7 bars
                                      to be well-defined. Below this we
                                      return an all-False / 觀望 result
                                      rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Thresholds (twstock-faithful — see module docstring) ──────────────────
MA_SHORT = 3
MA_MID = 6
PIVOT_SAMPLE_SIZE = 5
PIVOT_RECENT_BARS = 4
# MA6 needs 6 closes; the bias-pivot also needs a 5-long spread window which
# itself needs MA6 over 5 trailing windows → in practice ≥ 7 bars makes the
# whole pipeline (MAs, spread, pivot, [-2] look-backs) well-defined.
MIN_BARS = 7

VERDICT_BUY = "買進"
VERDICT_SELL = "賣出"
VERDICT_HOLD = "觀望"

BEST_BUY_WHY = (
    "量大收紅",
    "量縮價不跌",
    "三日均價由下往上",
    "三日均價大於六日均價",
)
BEST_SELL_WHY = (
    "量大收黑",
    "量縮價跌",
    "三日均價由上往下",
    "三日均價小於六日均價",
)


@dataclass(frozen=True)
class OHLCVSeries:
    """Chronological OHLCV series for one symbol (oldest first).

    All four lists MUST be the same length and ordered oldest→newest so that
    ``[-1]`` is the latest trading day. ``volumes`` maps to twstock's
    ``capacity``; ``closes`` to ``price``.
    """

    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]

    def __len__(self) -> int:
        return len(self.closes)

    def is_consistent(self) -> bool:
        n = len(self.closes)
        return (
            len(self.opens) == n
            and len(self.highs) == n
            and len(self.lows) == n
            and len(self.volumes) == n
        )


@dataclass
class BestFourPointResult:
    """Per-symbol four-point outcome.

    ``buy_points`` / ``sell_points`` are the *gated* triggered points (they
    already passed the bias-pivot gate). ``verdict`` is one of
    ``買進`` / ``賣出`` / ``觀望``. ``net_score`` = #buy − #sell.
    """

    verdict: str = VERDICT_HOLD
    buy_points: list[str] = field(default_factory=list)
    sell_points: list[str] = field(default_factory=list)
    net_score: int = 0
    # Why the verdict is HOLD / insufficient — empty string when a real
    # signal was produced. Useful for debugging the scan output.
    note: str = ""

    @property
    def has_signal(self) -> bool:
        return bool(self.buy_points) or bool(self.sell_points)


def _moving_average(data: list[float], days: int) -> list[float]:
    """Trailing simple MA, twstock-style (oldest→newest output).

    Mirrors twstock ``Analytics.moving_average``: for a series of length
    ``n`` returns ``n - days + 1`` values, each rounded to 2 dp. Returns an
    empty list when ``len(data) < days``.
    """
    if len(data) < days:
        return []
    result: list[float] = []
    for end in range(days, len(data) + 1):
        window = data[end - days : end]
        result.append(round(sum(window) / days, 2))
    return result


def _continuous(data: list[float]) -> int:
    """Signed run-length of the most-recent same-direction streak.

    Faithful to twstock ``Analytics.continuous``: compares consecutive
    values from the newest end backwards. ``+1`` per up-step, ``-1`` per
    down-step, counting how many of the most-recent steps share the latest
    step's direction. Returns 0 for a series too short to have a step.

    twstock builds ``diff`` newest-first as ``data[-i] > data[-i-1]`` and
    counts the leading run that matches ``diff[0]`` (the latest step). We
    reproduce that exactly.
    """
    if len(data) < 2:
        return 0
    diff = [1 if data[-i] > data[-i - 1] else -1 for i in range(1, len(data))]
    first = diff[0]
    cont = 0
    for v in diff:
        if v == first:
            cont += 1
        else:
            break
    return cont * first


def _bias_pivot(spread: list[float], *, position: bool) -> bool:
    """twstock ``ma_bias_ratio_pivot`` gate, returning just the boolean.

    ``spread`` is the (MA3 − MA6) series (oldest→newest). ``position=True``
    asks "did the spread recently TOP OUT above zero" (sell gate);
    ``position=False`` asks "did the spread recently BOTTOM OUT below zero"
    (buy gate). See module docstring for the three sub-conditions.
    """
    if len(spread) < PIVOT_SAMPLE_SIZE:
        return False
    sample = spread[-PIVOT_SAMPLE_SIZE:]

    if position:
        check_value = max(sample)
        pre_check = max(sample) > 0
    else:
        check_value = min(sample)
        pre_check = max(sample) < 0

    idx = sample.index(check_value)
    return (
        (PIVOT_SAMPLE_SIZE - idx) < PIVOT_RECENT_BARS
        and idx != (PIVOT_SAMPLE_SIZE - 1)
        and pre_check
    )


def _ma_bias_spread(closes: list[float], day1: int, day2: int) -> list[float]:
    """(MA{day1} − MA{day2}) series aligned at the newest end (oldest→newest).

    Faithful to twstock ``ma_bias_ratio``: the two MA series have different
    lengths, so it aligns them from the newest end and subtracts pairwise.
    """
    ma1 = _moving_average(closes, day1)
    ma2 = _moving_average(closes, day2)
    if not ma1 or not ma2:
        return []
    n = min(len(ma1), len(ma2))
    # Align at the newest end, subtract, return oldest→newest.
    return [ma1[-i] - ma2[-i] for i in range(1, n + 1)][::-1]


def _buy_points(series: OHLCVSeries, ma3: list[float], ma6: list[float]) -> list[bool]:
    closes, opens, vols = series.closes, series.opens, series.volumes
    p1 = vols[-1] > vols[-2] and closes[-1] > opens[-1]
    p2 = vols[-1] < vols[-2] and closes[-1] > opens[-2]
    p3 = _continuous(ma3) == 1
    p4 = ma3[-1] > ma6[-1]
    return [p1, p2, p3, p4]


def _sell_points(series: OHLCVSeries, ma3: list[float], ma6: list[float]) -> list[bool]:
    closes, opens, vols = series.closes, series.opens, series.volumes
    p1 = vols[-1] > vols[-2] and closes[-1] < opens[-1]
    p2 = vols[-1] < vols[-2] and closes[-1] < opens[-2]
    p3 = _continuous(ma3) == -1
    p4 = ma3[-1] < ma6[-1]
    return [p1, p2, p3, p4]


def compute_best_four_point(series: OHLCVSeries) -> BestFourPointResult:
    """Compute today's 四大買賣點 for one symbol.

    Pure function — deterministic over its input, no I/O. Returns a
    ``BestFourPointResult`` with the *gated* triggered buy/sell points and a
    three-way verdict. Insufficient / malformed data yields a 觀望 result
    with an explanatory ``note`` (never raises on short series).
    """
    if not series.is_consistent():
        return BestFourPointResult(note="ohlcv series length mismatch")
    if len(series) < MIN_BARS:
        return BestFourPointResult(note=f"insufficient bars ({len(series)} < {MIN_BARS})")

    ma3 = _moving_average(series.closes, MA_SHORT)
    ma6 = _moving_average(series.closes, MA_MID)
    if not ma3 or not ma6:
        return BestFourPointResult(note="moving averages unavailable")

    spread = _ma_bias_spread(series.closes, MA_SHORT, MA_MID)

    buy_gate = _bias_pivot(spread, position=False)
    sell_gate = _bias_pivot(spread, position=True)

    buy_flags = _buy_points(series, ma3, ma6)
    sell_flags = _sell_points(series, ma3, ma6)

    buy_points = (
        [BEST_BUY_WHY[i] for i, hit in enumerate(buy_flags) if hit]
        if (buy_gate and any(buy_flags))
        else []
    )
    sell_points = (
        [BEST_SELL_WHY[i] for i, hit in enumerate(sell_flags) if hit]
        if (sell_gate and any(sell_flags))
        else []
    )

    net = len(buy_points) - len(sell_points)
    if buy_points and net >= 1:
        verdict = VERDICT_BUY
    elif sell_points and net <= -1:
        verdict = VERDICT_SELL
    else:
        verdict = VERDICT_HOLD

    return BestFourPointResult(
        verdict=verdict,
        buy_points=buy_points,
        sell_points=sell_points,
        net_score=net,
    )
