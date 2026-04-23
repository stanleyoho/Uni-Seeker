from dataclasses import dataclass

from app.modules.screener.conditions import Condition, ConditionGroup


@dataclass(frozen=True)
class ScreenerPreset:
    key: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    conditions: ConditionGroup
    sort_by: str | None = None
    sort_order: str = "asc"


PRESETS: dict[str, ScreenerPreset] = {
    "oversold_bounce": ScreenerPreset(
        key="oversold_bounce",
        name_zh="超跌反彈候選",
        name_en="Oversold Bounce",
        description_zh="RSI < 30 且 KD K值 < 20，短期可能反彈",
        description_en="RSI < 30 and KD K < 20, potential short-term bounce",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op="<", value=30),
            Condition(indicator="KD_K", params={"k_period": 9}, op="<", value=20),
        ]),
        sort_by="RSI",
        sort_order="asc",
    ),
    "momentum": ScreenerPreset(
        key="momentum",
        name_zh="動能強勢股",
        name_en="Strong Momentum",
        description_zh="RSI > 60 且股價站上 MA20，趨勢向上",
        description_en="RSI > 60 and price above MA20, uptrend confirmed",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op=">", value=60),
            Condition(indicator="RSI", params={"period": 14}, op="<", value=80),
        ]),
        sort_by="RSI",
        sort_order="desc",
    ),
    "overbought_warning": ScreenerPreset(
        key="overbought_warning",
        name_zh="超買警示",
        name_en="Overbought Warning",
        description_zh="RSI > 80，短期有回檔壓力",
        description_en="RSI > 80, potential short-term pullback",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op=">", value=80),
        ]),
        sort_by="RSI",
        sort_order="desc",
    ),
    "bollinger_squeeze": ScreenerPreset(
        key="bollinger_squeeze",
        name_zh="布林收斂突破",
        name_en="Bollinger Squeeze",
        description_zh="股價觸及布林下軌且 RSI < 40，可能即將反彈",
        description_en="Price near lower Bollinger Band with RSI < 40",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op="<", value=40),
        ]),
        sort_by="RSI",
        sort_order="asc",
    ),
    "steady_growth": ScreenerPreset(
        key="steady_growth",
        name_zh="穩健成長股",
        name_en="Steady Growth",
        description_zh="RSI 在 40-60 之間，趨勢穩定不過熱",
        description_en="RSI between 40-60, stable trend without overheating",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op=">=", value=40),
            Condition(indicator="RSI", params={"period": 14}, op="<=", value=60),
        ]),
        sort_by="RSI",
        sort_order="asc",
    ),
    "volume_breakout": ScreenerPreset(
        key="volume_breakout",
        name_zh="爆量突破",
        name_en="Volume Breakout",
        description_zh="RSI > 55 且成交量放大，可能即將突破",
        description_en="RSI > 55 with volume surge, potential breakout",
        conditions=ConditionGroup(operator="AND", rules=[
            Condition(indicator="RSI", params={"period": 14}, op=">", value=55),
        ]),
        sort_by="RSI",
        sort_order="desc",
    ),
}
