"""Rebalance alert calculator.

Pure functions — no DB queries. Callers pass pre-fetched rules and positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class AllocationRuleData:
    """Input: one allocation rule for a symbol."""

    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal
    upper_threshold: Decimal
    is_active: bool


@dataclass
class PositionData:
    """Input: one position's current market value."""

    symbol: str
    market_value: Decimal


@dataclass
class AlertData:
    """Output: one triggered rebalance alert."""

    symbol: str
    current_weight: Decimal
    target_weight: Decimal
    deviation: Decimal  # current - target (positive = overweight)
    direction: Literal["over", "under"]


def compute_account_alerts(
    rules: list[AllocationRuleData],
    positions: list[PositionData],
    total_value: Decimal,
) -> list[AlertData]:
    """Return alerts for each active rule where current weight is outside threshold.

    Args:
        rules: Allocation rules to check (only active ones are evaluated).
        positions: Current positions with market values.
        total_value: Total portfolio value (sum of all positions). Must be > 0.

    Returns:
        List of AlertData for rules where |current - target| > threshold.
        Empty list if total_value is zero.
    """
    if total_value <= Decimal("0"):
        return []

    value_map = {pos.symbol: pos.market_value for pos in positions}
    alerts: list[AlertData] = []

    for rule in rules:
        if not rule.is_active:
            continue
        market_val = value_map.get(rule.symbol, Decimal("0"))
        current_weight = market_val / total_value
        deviation = current_weight - rule.target_weight

        if deviation > rule.upper_threshold:
            alerts.append(
                AlertData(
                    symbol=rule.symbol,
                    current_weight=current_weight.quantize(Decimal("0.0001")),
                    target_weight=rule.target_weight,
                    deviation=deviation.quantize(Decimal("0.0001")),
                    direction="over",
                )
            )
        elif deviation < -rule.lower_threshold:
            alerts.append(
                AlertData(
                    symbol=rule.symbol,
                    current_weight=current_weight.quantize(Decimal("0.0001")),
                    target_weight=rule.target_weight,
                    deviation=deviation.quantize(Decimal("0.0001")),
                    direction="under",
                )
            )

    return alerts
