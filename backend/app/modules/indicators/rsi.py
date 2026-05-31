"""RSI indicator — TA-Lib backed.

Wilder's RSI as originally published in 1978. The hand-rolled
implementation lived in this file pre-2026-06-01; it has been replaced
by a TA-Lib call (same Wilder smoothing, same default ``period=14``) via
the ``talib_wrappers.rsi`` adapter. Calling shape
(``calculate(closes, **params) -> IndicatorResult``) is unchanged so
every existing caller works as-is.

Parity with the old impl is asserted in
``tests/unit/modules/test_talib_parity.py::test_rsi_parity``.
"""

from typing import Any

from app.modules.indicators.base import IndicatorResult
from app.modules.indicators.talib_wrappers import rsi as talib_rsi


class RSIIndicator:
    name = "RSI"

    def calculate(self, closes: list[float], **params: Any) -> IndicatorResult:
        period = int(params.get("period", 14))
        # ``talib_rsi`` already returns ``list[float | None]`` of length
        # ``len(closes)`` with the warmup window padded with ``None``.
        return IndicatorResult(
            name=self.name,
            values={"RSI": talib_rsi(closes, period=period)},
        )
