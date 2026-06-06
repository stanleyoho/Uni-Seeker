"""Benchmark: per-symbol low-base scan loop vs vectorized batch (A2).

Not a pytest (timing assertions are flaky in CI) — a manual benchmark the
PR references for the speedup numbers. Run from ``backend/``:

    .venv/bin/python scripts/bench_low_base_scan.py

It builds a synthetic universe of M symbols (~300 closes each), then times:

  1. OLD path: per-symbol ``RSIIndicator.calculate`` (full list build) +
     ``calculate_low_base_score`` — exactly the loop the scan endpoint ran
     before this change.
  2. NEW path: ``rsi_last`` per symbol + a single ``compute_low_base_batch``
     vectorized pass.

It also asserts the two paths produce identical scores (parity), so the
benchmark doubles as a smoke test that the refactor preserves output.
"""

from __future__ import annotations

import random
import time

from app.modules.indicators.rsi import RSIIndicator
from app.modules.indicators.talib_wrappers import rsi_last
from app.modules.low_base.batch import compute_low_base_batch
from app.modules.low_base.scorer import calculate_low_base_score


def _make_universe(m: int, seed: int = 42) -> list[tuple[str, str, list[float]]]:
    rng = random.Random(seed)
    universe: list[tuple[str, str, list[float]]] = []
    for i in range(m):
        base = rng.uniform(20, 500)
        closes = [max(0.1, base + rng.gauss(0, base * 0.02)) for _ in range(300)]
        universe.append((f"{1000 + i}.TW", f"S{i}", closes))
    return universe


def _old_path(universe: list[tuple[str, str, list[float]]]) -> dict[str, float]:
    rsi_calc = RSIIndicator()
    out: dict[str, float] = {}
    for symbol, name, closes in universe:
        rsi_values = rsi_calc.calculate(closes, period=14).values["RSI"]
        current_rsi = None
        for v in reversed(rsi_values):
            if v is not None:
                current_rsi = v
                break
        score = calculate_low_base_score(symbol=symbol, name=name, closes=closes, rsi=current_rsi)
        out[symbol] = score.total_score
    return out


def _new_path(universe: list[tuple[str, str, list[float]]]) -> dict[str, float]:
    rows = [(s, n, c, rsi_last(c, period=14)) for s, n, c in universe]
    return {b.symbol: b.total_score for b in compute_low_base_batch(rows)}


def main() -> None:
    for m in (300, 1500):
        universe = _make_universe(m)

        t0 = time.perf_counter()
        old = _old_path(universe)
        t_old = time.perf_counter() - t0

        t0 = time.perf_counter()
        new = _new_path(universe)
        t_new = time.perf_counter() - t0

        # Parity: identical scores symbol-by-symbol.
        assert old == new, "parity mismatch between old and new scan paths"

        speedup = t_old / t_new if t_new else float("inf")
        print(
            f"M={m:>5} symbols | old(loop)={t_old * 1000:8.1f} ms | "
            f"new(vectorized)={t_new * 1000:8.1f} ms | speedup={speedup:5.1f}x | parity OK"
        )


if __name__ == "__main__":
    main()
