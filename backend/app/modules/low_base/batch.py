"""Vectorized cross-symbol low-base scan (A2 audit item).

Why this module exists
----------------------
The cross-symbol low-base scan (``GET /api/v1/low-base/scan``) ranks the
whole TW universe (~1500 symbols) by composite low-base score. The
read-path was already de-N+1'd at the DB layer (single batched price
query), but the *compute* still ran a per-symbol Python loop:

    for stock in universe:
        rsi = RSIIndicator().calculate(closes, period=14)   # ~hot
        score = calculate_low_base_score(closes, rsi=...)    # MA math

Profiling that loop on 1500 synthetic symbols (≈300 closes each) showed:

    full loop (rsi + scorer):  ~240 ms
      RSI wrapper:             ~155 ms   <-- dominant (65%)
      scorer:                   ~18 ms
        of which MA math:        ~9 ms

The RSI cost was NOT TA-Lib itself (raw ``talib.RSI`` last-value-only is
~11 ms for the same 1500 symbols). It was the per-symbol wrapper
overhead: ``talib_wrappers.rsi`` materializes a full
``list[float | None]`` of length N with a per-element ``math.isnan`` +
``round`` Python loop, for *every* bar of *every* symbol (≈450k Python
iterations), when the scan only needs the **last** RSI value per symbol.

This module applies the vectorbt *technique* — compute across symbols in
batched numpy passes instead of a Python per-symbol loop — WITHOUT taking
the vectorbt dependency (numpy is already a transitive dep used elsewhere
in ``app.modules.indicators``).

Parity contract
---------------
``compute_low_base_batch`` must produce results **identical** to calling
``app.modules.low_base.scorer.calculate_low_base_score`` once per symbol
with the same ``(closes, rsi)`` inputs (non-enhanced scan path: pe / pb /
roe / … all ``None``). This is a performance refactor — it must not
change scan output. The parity is asserted in
``tests/unit/modules/test_low_base_batch.py`` against the existing scorer.

Scope
-----
Only the **non-enhanced** scan path is vectorized here, because that is
the CPU-bound hot path. The enhanced path additionally performs
per-symbol *async I/O* (institutional flow fetch) and is therefore
I/O-bound, not a CPU-vectorization target — callers keep using the
per-symbol scorer for enhanced rows. ``compute_low_base_batch`` is a pure
function (no DB, no I/O) so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.modules.low_base.scorer import LowBaseScore

# These constants mirror the magic numbers baked into
# ``scorer._calculate_low_base_score_impl``. They are duplicated (not
# imported) on purpose: the scorer keeps them inline for readability, and
# the parity test guarantees the two implementations stay in lockstep. If
# the scorer's thresholds change, the parity test fails loudly here.
_MA240_PERIOD = 240
_MA60_PERIOD = 60
_RSI_LAST_ROUND = 4  # talib_wrappers rounds RSI to 4 dp before the scan reads it


@dataclass
class BatchScore:
    """Minimal per-symbol result of the vectorized scan.

    Mirrors the subset of ``LowBaseScore`` fields the scan endpoint
    actually reads. ``details`` carries the same keys the per-symbol
    scorer would populate for the non-enhanced path so the API response
    shape is unchanged.
    """

    symbol: str
    name: str
    total_score: float
    valuation_score: float
    price_position_score: float
    quality_score: float
    details: dict[str, object]


def _round2_vec(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Round to 2 dp using CPython's ``round`` (NOT ``np.round``) per element.

    numpy's rounding diverges from CPython's on tie-adjacent float64 values
    (e.g. CPython ``round(6.7749999999999995, 2) == 6.77`` but
    ``np.round`` yields 6.78). The scalar scorer uses CPython ``round``
    throughout, so to keep the vectorized path byte-identical we round the
    small number of relevant scalars with the same primitive. ``valid``
    marks positions that hold a real (non-NaN) value; the rest stay NaN.
    """
    out = values.copy()
    for i in range(out.shape[0]):
        if valid[i]:
            out[i] = round(float(values[i]), 2)
    return out


def _score_linear_vec(
    values: np.ndarray,
    best: float,
    worst: float,
    *,
    valid: np.ndarray,
) -> np.ndarray:
    """Vectorized twin of ``scorer._score_linear``.

    ``values`` is a float array; ``valid`` is a bool mask marking the
    positions that have a real value (the scalar scorer returns the
    *neutral* 50.0 for ``None``). Positions where ``valid`` is False get
    50.0, exactly like the scalar function's ``value is None`` branch.

    The branch structure matches ``_score_linear`` element-wise:
      * best == worst                  -> 50.0
      * best < worst  (lower better)   -> clamp, linear (worst-v)/(worst-best)
      * best > worst  (higher better)  -> clamp, linear (v-worst)/(best-worst)
    """
    out = np.full(values.shape, 50.0, dtype=np.float64)
    if best == worst:
        # Whole component is neutral regardless of value.
        return out

    if best < worst:  # lower is better
        # value <= best -> 100 ; value >= worst -> 0 ; else linear
        score = (worst - values) / (worst - best) * 100.0
        score = np.where(values <= best, 100.0, score)
        score = np.where(values >= worst, 0.0, score)
    else:  # higher is better
        score = (values - worst) / (best - worst) * 100.0
        score = np.where(values >= best, 100.0, score)
        score = np.where(values <= worst, 0.0, score)

    # Apply only where we actually have a value; otherwise neutral 50.0.
    return np.where(valid, score, out)


def compute_low_base_batch(
    rows: list[tuple[str, str, list[float], float | None]],
) -> list[BatchScore]:
    """Vectorized non-enhanced low-base scoring across many symbols.

    Parameters
    ----------
    rows:
        ``(symbol, name, closes, rsi)`` per symbol. ``closes`` is the
        chronological close series (oldest first); ``rsi`` is the latest
        RSI value the caller already computed (or ``None``). This matches
        exactly what the scan endpoint feeds ``calculate_low_base_score``
        on the non-enhanced path.

    Returns
    -------
    list[BatchScore]
        One result per input row, in input order, byte-identical in score
        to the per-symbol scorer. Disqualification is not applicable here
        (the non-enhanced scan passes no ``eps``), so no row is dropped.

    Notes
    -----
    Symbols have *variable-length* close series. We do not pad into a
    rectangular matrix (padding with sentinels would risk skewing
    ``max`` / ``mean``); instead each price-position component is computed
    with a vectorized reduction over the per-symbol slices. The win comes
    from (a) doing the MA / max / mean reductions in numpy C loops rather
    than Python ``sum()`` / ``max()``, and (b) collapsing the four
    price-position ``_score_linear`` calls into array ops over the whole
    universe at once.
    """
    n = len(rows)
    if n == 0:
        return []

    # --- Gather per-symbol scalar inputs via numpy reductions ---------------
    # ma240, ma60, last_close, high_240 are computed per symbol but using
    # numpy reductions on a single np.asarray per symbol (C-speed mean/max)
    # instead of Python sum()/max(). lengths drive the "enough data" masks.
    ma240 = np.full(n, np.nan, dtype=np.float64)
    ma60 = np.full(n, np.nan, dtype=np.float64)
    last_close = np.full(n, np.nan, dtype=np.float64)
    high_240 = np.full(n, np.nan, dtype=np.float64)
    lengths = np.zeros(n, dtype=np.int64)
    rsi_vals = np.full(n, np.nan, dtype=np.float64)
    rsi_valid = np.zeros(n, dtype=bool)

    for i, (_symbol, _name, closes, rsi) in enumerate(rows):
        arr = np.asarray(closes, dtype=np.float64)
        m = arr.shape[0]
        lengths[i] = m
        if m == 0:
            continue
        last_close[i] = arr[-1]
        if m >= _MA240_PERIOD:
            window = arr[-_MA240_PERIOD:]
            ma240[i] = window.mean()
            high_240[i] = window.max()
        if m >= _MA60_PERIOD:
            ma60[i] = arr[-_MA60_PERIOD:].mean()
        if rsi is not None:
            # The scan reads RSI from talib_wrappers, which already rounds
            # to 4 dp; the scalar scorer consumes that value as-is. Mirror
            # that exactly (caller passes the already-rounded value, so this
            # round is a no-op for real inputs but keeps the contract explicit).
            rsi_vals[i] = round(float(rsi), _RSI_LAST_ROUND)
            rsi_valid[i] = True

    has_240 = lengths >= _MA240_PERIOD
    has_60 = lengths >= _MA60_PERIOD

    # --- Price-position components (vectorized) -----------------------------
    # Each component is an array of per-symbol scores plus a bool mask of
    # which symbols contribute it (matching the scalar scorer's append
    # guards). price_position_score = mean of contributing components, or
    # 50.0 when none contribute.
    comp_scores: list[np.ndarray] = []
    comp_masks: list[np.ndarray] = []

    # MA240 deviation: scorer caps deviation at -30 then scores -20..20.
    # calculate_ma_deviation returns None when ma == 0, so a zero MA does
    # NOT contribute (mask it out) — matches the scalar guard.
    #
    # Rounding parity: ``calculate_ma_deviation`` rounds deviation_pct with
    # CPython ``round`` and that *rounded* value feeds BOTH the score input
    # and the details dict. We mirror that with ``_round2_vec`` (CPython
    # ``round`` per element) rather than ``np.round`` so the 0.01 tie-edge
    # cases match the scalar path exactly.
    ma240_nonzero = has_240 & (ma240 != 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ma240_dev_raw = (last_close - ma240) / ma240 * 100.0
    ma240_dev = _round2_vec(ma240_dev_raw, ma240_nonzero)
    ma240_dev_capped = np.maximum(ma240_dev, -30.0)
    ma240_comp = _score_linear_vec(ma240_dev_capped, -20.0, 20.0, valid=ma240_nonzero)
    comp_scores.append(ma240_comp)
    comp_masks.append(ma240_nonzero)

    # MA60 deviation: scores -15..15, also None when ma == 0.
    ma60_nonzero = has_60 & (ma60 != 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ma60_dev_raw = (last_close - ma60) / ma60 * 100.0
    ma60_dev = _round2_vec(ma60_dev_raw, ma60_nonzero)
    ma60_comp = _score_linear_vec(ma60_dev, -15.0, 15.0, valid=ma60_nonzero)
    comp_scores.append(ma60_comp)
    comp_masks.append(ma60_nonzero)

    # RSI: scores 20..70 (lower better). Contributes wherever rsi present.
    rsi_comp = _score_linear_vec(rsi_vals, 20.0, 70.0, valid=rsi_valid)
    comp_scores.append(rsi_comp)
    comp_masks.append(rsi_valid)

    # Drop from 240d high: scorer only computes this when high_240 > 0.
    # drop < -50 -> fixed 20.0 ; else linear -25..0.
    drop_valid = has_240 & (high_240 > 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        drop_pct = (last_close - high_240) / high_240 * 100.0
    drop_linear = _score_linear_vec(drop_pct, -25.0, 0.0, valid=drop_valid)
    drop_comp = np.where(drop_pct < -50.0, 20.0, drop_linear)
    drop_comp = np.where(drop_valid, drop_comp, 50.0)
    comp_scores.append(drop_comp)
    comp_masks.append(drop_valid)

    # price_position_score = mean of contributing components, else 50.0.
    score_stack = np.vstack(comp_scores)  # (n_components, n_symbols)
    mask_stack = np.vstack(comp_masks)
    contrib_sum = np.where(mask_stack, score_stack, 0.0).sum(axis=0)
    contrib_count = mask_stack.sum(axis=0)
    price_position = np.where(
        contrib_count > 0,
        contrib_sum / np.where(contrib_count > 0, contrib_count, 1),
        50.0,
    )

    # valuation_score and quality_score are constant 50.0 on the
    # non-enhanced scan (no pe/pb/roe/... supplied) — matches the scalar
    # scorer's "empty components -> 50.0" branches.
    valuation = np.full(n, 50.0, dtype=np.float64)
    quality = np.full(n, 50.0, dtype=np.float64)

    # Composite (original 40/30/30 weights — non-enhanced path). Computed
    # from the *unrounded* sub-scores, exactly like the scalar scorer
    # (scorer.py builds ``total`` from the unrounded locals, then rounds
    # each field independently in the LowBaseScore constructor).
    total = valuation * 0.4 + price_position * 0.3 + quality * 0.3

    # --- Materialize results (details dict mirrors scalar scorer) -----------
    # CRITICAL parity detail: round with Python's built-in ``round`` on the
    # scalar values, NOT ``np.round``. numpy's rounding diverges from
    # CPython's for tie-adjacent float64 values (e.g. 6.7749999999999995 →
    # CPython round=6.77, np.round=6.78). The scalar scorer uses ``round``,
    # so we must too, or parity breaks by 0.01 on edge values.
    results: list[BatchScore] = []
    for i, (symbol, name, _closes, _rsi) in enumerate(rows):
        details: dict[str, object] = {}
        if ma240_nonzero[i]:
            # ma240_dev already CPython-rounded to 2 dp by _round2_vec.
            details["ma240_deviation"] = float(ma240_dev[i])
        if ma60_nonzero[i]:
            details["ma60_deviation"] = float(ma60_dev[i])
        if rsi_valid[i]:
            details["rsi"] = float(rsi_vals[i])
        if drop_valid[i]:
            details["drop_from_high_240d"] = round(float(drop_pct[i]), 2)

        results.append(
            BatchScore(
                symbol=symbol,
                name=name,
                total_score=round(float(total[i]), 2),
                valuation_score=round(float(valuation[i]), 2),
                price_position_score=round(float(price_position[i]), 2),
                quality_score=round(float(quality[i]), 2),
                details=details,
            )
        )
    return results


def batch_score_to_low_base_score(b: BatchScore) -> LowBaseScore:
    """Adapt a :class:`BatchScore` to the public :class:`LowBaseScore`.

    Lets callers that expect the scorer's dataclass consume batch results
    without branching. Enhanced-only fields stay ``None`` (the batch path
    is non-enhanced by construction).
    """
    return LowBaseScore(
        symbol=b.symbol,
        name=b.name,
        total_score=b.total_score,
        valuation_score=b.valuation_score,
        price_position_score=b.price_position_score,
        quality_score=b.quality_score,
        details=b.details,
    )
