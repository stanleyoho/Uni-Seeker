from dataclasses import dataclass

from app.models.price import StockPrice
from app.modules.indicators.registry import IndicatorRegistry
from app.modules.screener.conditions import ConditionGroup


@dataclass
class ScreenResult:
    symbol: str
    indicator_values: dict[str, float]


class ScreenerEngine:
    def __init__(self, registry: IndicatorRegistry) -> None:
        self._registry = registry

    def screen(
        self,
        stocks_prices: dict[str, list[StockPrice]],
        conditions: ConditionGroup,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> list[ScreenResult]:
        results: list[ScreenResult] = []
        needed_indicators = {rule.indicator for rule in conditions.rules}

        for symbol, prices in stocks_prices.items():
            if not prices:
                continue

            closes = [float(p.close) for p in prices]
            highs = [float(p.high) for p in prices]
            lows = [float(p.low) for p in prices]
            volumes = [p.volume for p in prices]

            indicator_values: dict[str, float] = {}

            for ind_name in needed_indicators:
                registry_name = ind_name.split("_")[0] if "_" in ind_name else ind_name
                try:
                    indicator = self._registry.get(registry_name)
                except KeyError:
                    continue

                params: dict[str, object] = {}
                for rule in conditions.rules:
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

            if conditions.evaluate(indicator_values):
                results.append(ScreenResult(symbol=symbol, indicator_values=indicator_values))

        if sort_by and results:
            results.sort(
                key=lambda r: r.indicator_values.get(sort_by, 0),
                reverse=(sort_order == "desc"),
            )
        return results
