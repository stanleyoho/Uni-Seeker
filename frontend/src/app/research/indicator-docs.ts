/**
 * Plain-Chinese tooltip definitions for each technical indicator card
 * in the unified `/research` page. Shown when the user hovers / taps
 * the ℹ icon next to a condition card.
 *
 * Keep each definition to 1-2 sentences. Goal is "what does this
 * indicator mean" in plain terms, NOT mathematical formulas — those
 * belong in long-form education docs, not a tooltip.
 *
 * `backendStrategyKey` is the value sent in the
 * `POST /api/v1/scanner/scan` request's `strategy_keys[]`. `null`
 * means there is no registered backend strategy today — the card is
 * still rendered (Stanley asked for it) but is greyed out and cannot
 * be enabled. See `templates.ts` BACKEND GAP comment.
 */

export type IndicatorKey =
  | "rsi"
  | "macd"
  | "bollinger"
  | "kd"
  | "sma_cross"
  | "volume";

export interface IndicatorDoc {
  /** Display name shown on the card header. */
  label: string;
  /** zh-TW 1-2 sentence definition. */
  description: string;
  /**
   * Backend `strategy_keys[]` value (registered in
   * `backend/app/modules/strategy/__init__.py`). `null` = no backend
   * strategy — UI marks the card unavailable.
   */
  backendStrategyKey: string | null;
}

export const INDICATOR_DOCS: Record<IndicatorKey, IndicatorDoc> = {
  rsi: {
    label: "RSI",
    description:
      "相對強弱指標。計算近 N 日漲幅佔總波動的比例，數值 0-100。一般以 70 以上視為超買、30 以下視為超賣。",
    backendStrategyKey: "rsi_oversold",
  },
  macd: {
    label: "MACD",
    description:
      "指數平滑異同移動平均。觀察快線（DIF）與慢線（DEA）的黃金 / 死亡交叉，是常見的中期動能指標。",
    backendStrategyKey: "macd_crossover",
  },
  bollinger: {
    label: "Bollinger Bands",
    description:
      "布林通道。以 20 日均線為中軸、上下各加減兩倍標準差。價格貼上軌代表強勢，通道寬度收斂代表波動度壓縮、可能即將變盤。",
    backendStrategyKey: "bollinger_bounce",
  },
  kd: {
    label: "KD",
    description:
      "隨機指標。比較收盤價在近 N 日高低區間內的相對位置，K 與 D 的交叉常用來偵測短線反轉。",
    // TODO(stanley): backend has no `kd_*` strategy registered yet —
    // tracked as part of the unified-research backend gap.
    backendStrategyKey: null,
  },
  sma_cross: {
    label: "SMA Cross",
    description:
      "簡單移動平均線交叉。短期均線由下往上穿越長期均線稱黃金交叉，反之為死亡交叉，用來判斷中長期趨勢轉折。",
    backendStrategyKey: "ma_crossover",
  },
  volume: {
    label: "Volume",
    description:
      "成交量突破。將當日量能與近 20 日平均量比較，倍數越高代表市場關注度突然放大，常配合價格訊號使用。",
    // TODO(stanley): backend has no standalone `volume_*` strategy —
    // tracked as part of the unified-research backend gap.
    backendStrategyKey: null,
  },
};

export const INDICATOR_ORDER: IndicatorKey[] = [
  "rsi",
  "macd",
  "bollinger",
  "kd",
  "sma_cross",
  "volume",
];
