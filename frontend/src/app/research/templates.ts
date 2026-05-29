/**
 * Strategy templates for the unified `/research` (Scan) page.
 *
 * Each template is a pre-baked combination of strategy cards + threshold
 * values that the user can apply in one click. Selecting a template
 * replaces the current `ConditionState[]` in the page; selecting "custom"
 * clears everything and lets the user build from scratch.
 *
 * ---------------------------------------------------------------------
 * Strategy key mapping (frontend label -> backend `strategy_keys` value)
 * ---------------------------------------------------------------------
 * The backend (`app.modules.strategy.__init__`) registers these keys:
 *
 *   - ma_crossover      (SMA cross)
 *   - rsi_oversold      (RSI low rebound)
 *   - macd_crossover    (MACD)
 *   - bollinger_bounce  (Bollinger Bands)
 *   - bias_reversal     (price-vs-MA bias)
 *   - rsi_bias_combo    (RSI + bias)
 *   - institutional_follow, margin_divergence, foreign_trust_sync,
 *     ownership_concentration, margin_overleverage  (chip-data)
 *
 * BACKEND GAP: the old Signal Scanner UI exposed `KD` and `Volume`
 * strategy chips, but there are NO matching registered strategies on
 * the backend. The unified form therefore renders KD / Volume cards
 * (because Stanley asked for them) but marks them as `unavailable` so
 * they cannot be sent to `/scanner/scan` and trigger a 400. The PR body
 * documents this gap.
 *
 * BACKEND GAP #2: the backend `SignalScanRequest` schema only accepts
 * `symbols`, `strategy_keys`, and `limit`. It does NOT accept per-strategy
 * threshold params (e.g. RSI level, BB width). The threshold values
 * captured in the UI are therefore stored in the request state but ONLY
 * the `strategy_keys` derived from enabled cards are forwarded today. The
 * thresholds are ready to wire the day the backend grows a `thresholds`
 * dict on `SignalScanRequest`.
 */

import type { IndicatorKey } from "./indicator-docs";

// ---- Threshold params per indicator -----------------------------------

export type RsiParams = { op: "<" | ">"; value: number };
export type MacdParams = { signal: "bullish_cross" | "bearish_cross" };
export type BollingerParams = { widthPct: number; breakout: "upper" | "lower" };
export type KdParams = { op: "<" | ">"; level: number };
export type SmaCrossParams = { shortPeriod: number; longPeriod: number };
export type VolumeParams = { multipleOf20dAvg: number };

export type IndicatorParams =
  | { kind: "rsi"; params: RsiParams }
  | { kind: "macd"; params: MacdParams }
  | { kind: "bollinger"; params: BollingerParams }
  | { kind: "kd"; params: KdParams }
  | { kind: "sma_cross"; params: SmaCrossParams }
  | { kind: "volume"; params: VolumeParams };

export interface StrategyConditionPreset {
  /** Which indicator card is enabled. */
  indicator: IndicatorKey;
  /** Threshold params, defaulted to a sensible value. */
  params: IndicatorParams["params"];
}

export interface TemplateDefinition {
  id: string;
  /** zh-TW label shown on the chip. */
  label: string;
  /** 1-2 sentence plain-Chinese description shown in tooltip. */
  description: string;
  /**
   * Strategies that the template enables, in order. Empty array means
   * `Custom` — clear everything.
   */
  strategies: StrategyConditionPreset[];
}

export const TEMPLATES: TemplateDefinition[] = [
  {
    id: "golden_cross",
    label: "黃金交叉",
    description: "短期均線（如 5 日）由下往上穿越長期均線（如 20 日），且伴隨量能放大，常被視為多頭啟動訊號。",
    strategies: [
      { indicator: "sma_cross", params: { shortPeriod: 5, longPeriod: 20 } },
      { indicator: "volume", params: { multipleOf20dAvg: 1.5 } },
    ],
  },
  {
    id: "volume_breakout",
    label: "量價突破",
    description: "成交量達 20 日平均的 1.5 倍以上，且收盤價突破近 20 日高點，代表買盤積極介入。",
    strategies: [
      { indicator: "volume", params: { multipleOf20dAvg: 1.5 } },
      { indicator: "sma_cross", params: { shortPeriod: 5, longPeriod: 20 } },
    ],
  },
  {
    id: "bollinger_squeeze_breakout",
    label: "布林收斂後突破",
    description: "布林通道寬度收窄至 5% 以內代表波動度壓縮，當收盤價突破上軌時往往伴隨趨勢啟動。",
    strategies: [
      { indicator: "bollinger", params: { widthPct: 5, breakout: "upper" } },
    ],
  },
  {
    id: "rsi_oversold_rebound",
    label: "RSI 超賣反彈",
    description: "RSI 低於 30 視為超賣，當天收盤價高於前一日收盤代表反彈訊號出現。",
    strategies: [
      { indicator: "rsi", params: { op: "<", value: 30 } },
    ],
  },
  {
    id: "kd_golden_cross",
    label: "KD 黃金交叉",
    description: "K 線在 30 以下由下往上穿越 D 線，常被視為低檔反轉訊號（注意：後端尚未提供 KD 策略，暫無法送出掃描）。",
    strategies: [
      { indicator: "kd", params: { op: "<", level: 30 } },
    ],
  },
  {
    id: "custom",
    label: "Custom 自訂",
    description: "清空所有條件，自由組合想要的指標。",
    strategies: [],
  },
];

export function findTemplate(id: string): TemplateDefinition | undefined {
  return TEMPLATES.find((t) => t.id === id);
}
