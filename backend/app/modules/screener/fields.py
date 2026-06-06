"""Field allowlist + metadata for the composable screener Query DSL (A2).

Why an explicit allowlist
=========================
The DSL endpoint accepts a client-supplied ``field`` per clause. Without an
allowlist a caller could pass an arbitrary string that the engine would
forward straight into ``IndicatorRegistry.get`` /
``indicator_values.get`` — at best a silent no-match, at worst a vector
for probing internals. The screener never builds SQL from the field name
(it screens in-memory over pre-fetched price series), so this is not a SQL
injection surface, but the allowlist still keeps the contract honest:
unknown fields fail loud with a 422 instead of silently returning zero
matches.

How fields map onto the engine
==============================
``ScreenerEngine.screen`` resolves each ``Condition.indicator`` to a
registered :class:`Indicator` by splitting on the first ``_``
(``"KD_K".split("_")[0] == "KD"``) and then reads the computed value out
of ``indicator_values`` under that same key. A *field* in the DSL is
therefore exactly one of those engine-facing keys. The catalogue below is
the single source of truth shared by:

  * the DSL compiler (:mod:`app.modules.screener.dsl`) — validation, and
  * the ``GET /screener/fields`` metadata endpoint — UI dropdown.

Each entry carries the registry indicator it resolves to plus a default
params dict so a bare ``{field: "RSI"}`` clause computes with sensible
defaults (period 14, etc.) without the client having to know indicator
internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    """One DSL-addressable field.

    ``key``       — the engine-facing key (== ``Condition.indicator``).
    ``indicator`` — the registry indicator it resolves to.
    ``label``     — human label for the UI dropdown.
    ``params``    — default indicator params applied when the clause does
                    not override them.
    ``unit``      — optional display hint (``"pct"``, ``"price"`` …).
    """

    key: str
    indicator: str
    label: str
    params: dict[str, Any] = dataclass_field(default_factory=dict)
    unit: str | None = None


# Single source of truth. Keys MUST stay consistent with the value keys
# produced by ``ScreenerEngine.screen`` (see module docstring). Only the
# numeric, comparable outputs are exposed — pattern / signal indicators
# (PATTERN, PV new_high_low) emit categorical sentinels that don't slot
# into a ``lt/gt`` comparison cleanly, so they're intentionally omitted
# from the v1 DSL allowlist (descoped, see PR notes).
_FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("RSI", "RSI", "RSI (14)", {"period": 14}),
    FieldSpec("BIAS", "BIAS", "Bias %", {"period": 20}, unit="pct"),
    FieldSpec("MACD", "MACD", "MACD line", {}),
    FieldSpec("MACD_signal", "MACD", "MACD signal", {}),
    FieldSpec("MACD_histogram", "MACD", "MACD histogram", {}),
    FieldSpec("KD_K", "KD", "KD %K", {"k_period": 9}),
    FieldSpec("KD_D", "KD", "KD %D", {"k_period": 9}),
    FieldSpec("MA", "MA", "Moving Average (20)", {"period": 20}, unit="price"),
    FieldSpec("BB_upper", "BB", "Bollinger upper", {}, unit="price"),
    FieldSpec("BB_middle", "BB", "Bollinger middle", {}, unit="price"),
    FieldSpec("BB_lower", "BB", "Bollinger lower", {}, unit="price"),
    FieldSpec("VOL_VMA", "VOL", "Volume MA", {"indicator_type": "VMA"}),
)


FIELD_SPECS: dict[str, FieldSpec] = {spec.key: spec for spec in _FIELD_SPECS}

# Frozen allowlist used by the DSL validator. ``frozenset`` so it can't be
# mutated at runtime by a caller holding a reference.
ALLOWED_FIELDS: frozenset[str] = frozenset(FIELD_SPECS)


def is_allowed_field(name: str) -> bool:
    """Return True iff ``name`` is a DSL-addressable field."""
    return name in ALLOWED_FIELDS


def get_field_spec(name: str) -> FieldSpec:
    """Return the :class:`FieldSpec` for ``name``.

    Raises :class:`KeyError` if the field is not in the allowlist — callers
    that have already validated via :func:`is_allowed_field` will never hit
    this.
    """
    return FIELD_SPECS[name]
