"""Parity + behaviour tests for the vectorized low-base batch scan.

The single most important property is **output parity**: the vectorized
``compute_low_base_batch`` must produce results identical to calling the
existing per-symbol ``calculate_low_base_score`` on the non-enhanced scan
path. This is a performance refactor; it must not change scan output.

The parity test is the regression guard against the old logic — it
literally re-runs the scalar scorer and asserts field-by-field equality.
"""

from __future__ import annotations

import random

from app.modules.low_base.batch import (
    BatchScore,
    batch_score_to_low_base_score,
    compute_low_base_batch,
)
from app.modules.low_base.scorer import calculate_low_base_score


def _scalar_row(symbol: str, name: str, closes: list[float], rsi: float | None) -> dict[str, object]:
    """Run the existing per-symbol scorer (the old path) for one symbol.

    Returns the comparable fields as a plain dict so the parity assertion
    is symmetric with the BatchScore fields.
    """
    s = calculate_low_base_score(symbol=symbol, name=name, closes=closes, rsi=rsi)
    return {
        "symbol": s.symbol,
        "name": s.name,
        "total_score": s.total_score,
        "valuation_score": s.valuation_score,
        "price_position_score": s.price_position_score,
        "quality_score": s.quality_score,
        "details": s.details,
    }


def _assert_parity(batch: BatchScore, scalar: dict[str, object]) -> None:
    assert batch.symbol == scalar["symbol"]
    assert batch.name == scalar["name"]
    assert batch.total_score == scalar["total_score"], (
        f"total_score mismatch for {batch.symbol}: "
        f"batch={batch.total_score} scalar={scalar['total_score']}"
    )
    assert batch.valuation_score == scalar["valuation_score"]
    assert batch.price_position_score == scalar["price_position_score"], (
        f"price_position mismatch for {batch.symbol}: "
        f"batch={batch.price_position_score} scalar={scalar['price_position_score']}"
    )
    assert batch.quality_score == scalar["quality_score"]
    # Detail keys + values must match exactly (the API serializes these).
    assert batch.details == scalar["details"], (
        f"details mismatch for {batch.symbol}: "
        f"batch={batch.details} scalar={scalar['details']}"
    )


# ---------------------------------------------------------------------------
# (a) Identical results vs the old per-symbol path on a fixture
# ---------------------------------------------------------------------------


def test_parity_strong_low_base_candidate() -> None:
    closes = [120.0] * 200 + [float(120 - i * 0.3) for i in range(60)]
    rows = [("TEST.TW", "Test", closes, 28.0)]
    batch = compute_low_base_batch(rows)
    scalar = _scalar_row("TEST.TW", "Test", closes, 28.0)
    _assert_parity(batch[0], scalar)


def test_parity_overvalued() -> None:
    closes = [float(100 + i * 0.5) for i in range(260)]
    rows = [("HIGH.TW", "High", closes, 75.0)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("HIGH.TW", "High", closes, 75.0))


def test_parity_short_series_no_ma() -> None:
    """< 60 closes: no MA components, score driven by RSI only."""
    closes = [float(100 - i * 0.2) for i in range(30)]
    rows = [("MIN.TW", "Minimal", closes, 45.0)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("MIN.TW", "Minimal", closes, 45.0))


def test_parity_no_rsi() -> None:
    """rsi=None: RSI component absent on both paths."""
    closes = [float(100 - i * 0.1) for i in range(120)]
    rows = [("NORSI.TW", "NoRsi", closes, None)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("NORSI.TW", "NoRsi", closes, None))


def test_parity_60_to_239_closes() -> None:
    """60 <= len < 240: MA60 + RSI contribute, MA240 + drop do not."""
    closes = [float(80 + i * 0.05) for i in range(180)]
    rows = [("MID.TW", "Mid", closes, 55.0)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("MID.TW", "Mid", closes, 55.0))


def test_parity_drop_from_high_extreme() -> None:
    """drop < -50% hits the fixed-20 branch — exercise it explicitly."""
    closes = [200.0] * 240 + []  # all-high then ...
    closes = [200.0] * 239 + [80.0]  # last close -60% from high
    rows = [("CRASH.TW", "Crash", closes, 30.0)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("CRASH.TW", "Crash", closes, 30.0))


def test_parity_all_zero_closes() -> None:
    """All-zero series: MA==0 / high==0 guards must mirror the scalar path
    (Bug-1 ZeroDivision regression shape)."""
    closes = [0.0] * 240
    rows = [("ZERO.TW", "Zero", closes, None)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("ZERO.TW", "Zero", closes, None))


def test_parity_mixed_zero_prefix() -> None:
    closes = [0.0] * 100 + [50.0] * 140
    rows = [("ZMIX.TW", "ZMix", closes, 40.0)]
    batch = compute_low_base_batch(rows)
    _assert_parity(batch[0], _scalar_row("ZMIX.TW", "ZMix", closes, 40.0))


# ---------------------------------------------------------------------------
# (b) N symbols in ONE vectorized pass, all parity-exact
# ---------------------------------------------------------------------------


def test_parity_many_symbols_one_pass() -> None:
    """Randomized universe of N symbols, computed in a single batch call,
    every row identical to the old per-symbol scorer."""
    rng = random.Random(20260606)
    rows: list[tuple[str, str, list[float], float | None]] = []
    for i in range(200):
        length = rng.choice([30, 60, 120, 180, 240, 300])
        base = rng.uniform(10, 500)
        closes = [max(0.0, base + rng.gauss(0, base * 0.03)) for _ in range(length)]
        rsi: float | None = round(rng.uniform(10, 90), 4) if rng.random() > 0.15 else None
        rows.append((f"S{i}.TW", f"Name{i}", closes, rsi))

    batch = compute_low_base_batch(rows)
    assert len(batch) == len(rows)
    for b, (sym, name, closes, rsi) in zip(batch, rows, strict=True):
        _assert_parity(b, _scalar_row(sym, name, closes, rsi))


def test_empty_input() -> None:
    assert compute_low_base_batch([]) == []


def test_order_preserved() -> None:
    rows = [
        ("A.TW", "A", [100.0] * 240, 30.0),
        ("B.TW", "B", [50.0] * 240, 70.0),
        ("C.TW", "C", [10.0] * 60, None),
    ]
    batch = compute_low_base_batch(rows)
    assert [b.symbol for b in batch] == ["A.TW", "B.TW", "C.TW"]


def test_adapter_to_low_base_score() -> None:
    rows = [("A.TW", "A", [100.0] * 240, 30.0)]
    b = compute_low_base_batch(rows)[0]
    lbs = batch_score_to_low_base_score(b)
    assert lbs.symbol == b.symbol
    assert lbs.total_score == b.total_score
    assert lbs.institutional_technical_score is None
    assert lbs.disqualified is False
