"""Alpha158-style quantitative factor zoo (A2 audit item).

This module implements a *bounded, representative* set of cross-sectional
price/volume factors inspired by Microsoft Qlib's **Alpha158** handcrafted
feature family. It is deliberately **NOT** a dependency on ``qlib`` (a heavy
ML framework that is a CI-install nightmare): Qlib is the *inspiration*, and
every factor here is re-implemented from first principles over a single
symbol's OHLCV using only ``pandas`` / ``numpy`` / TA-Lib — all of which
already ship in this repo.

Design contract
===============
* **Pure functions.** Each factor is a free function taking an OHLCV
  :class:`pandas.DataFrame` (columns ``open/high/low/close/volume``, oldest
  bar first) and returning a single ``float`` computed on the *latest* bar,
  or ``None`` when there is insufficient lookback. No I/O, no global state.
* **Documented formula.** Every factor's docstring states the exact formula
  and, where it diverges from the Qlib original, says so explicitly (see the
  honesty notes in :mod:`app.modules.factors.alpha158`).
* **Layering.** Lives under ``app.modules`` (domain logic). It imports only
  third-party libs + sibling factor helpers — never ``app.api`` /
  ``app.services`` — so it satisfies the import-linter "domain modules must
  not import the API layer" contract.

The public surface is the :data:`FACTORS` registry (name -> spec) plus
:func:`compute_factor_vector`, which evaluates the whole set for one symbol.
"""

from __future__ import annotations

from app.modules.factors.alpha158 import (
    FACTORS,
    FactorSpec,
    beta_to_index,
    composite_momentum_score,
    compute_factor_vector,
    klen,
    klow,
    kmid,
    kup,
    ma_ratio,
    max_position,
    min_position,
    roc,
    rsi_factor,
    std_factor,
    volume_ratio,
    williams_r,
)

__all__ = [
    "FACTORS",
    "FactorSpec",
    "beta_to_index",
    "composite_momentum_score",
    "compute_factor_vector",
    "klen",
    "klow",
    "kmid",
    "kup",
    "ma_ratio",
    "max_position",
    "min_position",
    "roc",
    "rsi_factor",
    "std_factor",
    "volume_ratio",
    "williams_r",
]
