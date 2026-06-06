from dataclasses import dataclass

from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.screener.conditions import (
    Condition,
    ConditionGroup,
    NestedConditionGroup,
)


@dataclass
class ScreenResult:
    symbol: str
    indicator_values: dict[str, float]


class ScreenerEngine:
    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry

    def _compute_indicator_values(
        self,
        prices: list[StockPrice],
        rules: list[Condition],
    ) -> dict[str, float]:
        """Compute the latest value for every indicator referenced by ``rules``.

        Shared by the flat ``screen`` path and the nested ``screen_dsl``
        path so there is exactly one place where indicators are evaluated
        against a symbol's price series (no duplicated compute logic).
        """
        closes = [float(p.close) for p in prices]
        highs = [float(p.high) for p in prices]
        lows = [float(p.low) for p in prices]
        volumes = [p.volume for p in prices]

        needed_indicators = {rule.indicator for rule in rules}
        indicator_values: dict[str, float] = {}

        for ind_name in needed_indicators:
            registry_name = ind_name.split("_")[0] if "_" in ind_name else ind_name
            try:
                indicator = self._registry.get(registry_name)
            except KeyError:
                continue

            params: dict[str, object] = {}
            for rule in rules:
                if rule.indicator == ind_name:
                    params = dict(rule.params)
                    break

            if registry_name == "KD":
                params["highs"] = highs
                params["lows"] = lows
            if registry_name == "VOL":
                params["volumes"] = volumes

            result = indicator.calculate(closes, **params)
            for key, values in result.values.items():
                target_key = ind_name if ind_name != registry_name else key
                for v in reversed(values):
                    if v is not None:
                        indicator_values[target_key] = float(v)
                        break

        return indicator_values

    @staticmethod
    def _sorted(
        results: list[ScreenResult],
        sort_by: str | None,
        sort_order: str,
    ) -> list[ScreenResult]:
        if sort_by and results:
            results.sort(
                key=lambda r: r.indicator_values.get(sort_by, 0),
                reverse=(sort_order == "desc"),
            )
        return results

    def screen(
        self,
        stocks_prices: dict[str, list[StockPrice]],
        conditions: ConditionGroup,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[ScreenResult]:
        results: list[ScreenResult] = []

        for symbol, prices in stocks_prices.items():
            if not prices:
                continue
            indicator_values = self._compute_indicator_values(prices, conditions.rules)
            if conditions.evaluate(indicator_values):  # type: ignore[arg-type]
                results.append(ScreenResult(symbol=symbol, indicator_values=indicator_values))

        return self._sorted(results, sort_by, sort_order)

    def screen_dsl(
        self,
        stocks_prices: dict[str, list[StockPrice]],
        group: NestedConditionGroup,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[ScreenResult]:
        """Screen using a composable nested AND/OR group (Query DSL, A2).

        Identical indicator-compute path as :meth:`screen`; only the
        boolean evaluation differs (recursive vs single-level), and that
        lives entirely in :class:`NestedConditionGroup.evaluate`.
        """
        leaf_rules = group.conditions()
        results: list[ScreenResult] = []

        for symbol, prices in stocks_prices.items():
            if not prices:
                continue
            indicator_values = self._compute_indicator_values(prices, leaf_rules)
            if group.evaluate(indicator_values):  # type: ignore[arg-type]
                results.append(ScreenResult(symbol=symbol, indicator_values=indicator_values))

        return self._sorted(results, sort_by, sort_order)
