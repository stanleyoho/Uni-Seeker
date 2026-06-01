/**
 * 5-level sentiment classifier — shared signal language across surfaces.
 *
 * Inspired by twetf.com's emoji + 5-color taxonomy. Replaces the legacy
 * 2-color (green up / red down) treatment with a more readable scale
 * that is also color-blind friendlier (emoji shape + Tailwind hue).
 *
 * Levels (threshold uses percent change, e.g. -1.23 for -1.23 %):
 *
 *   過熱  changePercent >= +1            🔴 red-400      ▲
 *   上漲  +0.1 <= changePercent < +1     🟠 orange-400   ▲
 *   平    -0.1 <  changePercent < +0.1   ⚪ gray-400     —
 *   下跌  -1   <  changePercent <= -0.1  🔵 sky-400      ▼
 *   深跌  changePercent <= -1            🟣 purple-400   ▼
 *
 * Boundary convention (matches the user's spec verbatim):
 *   - Exactly +1.0 % → 過熱 (heated).
 *   - Exactly +0.1 % → 上漲.
 *   - Exactly -0.1 % → 下跌.
 *   - Exactly -1.0 % → 深跌.
 *   - 0 % → 平.
 *
 * NaN / undefined / null inputs collapse to "平" with the muted colour
 * and em-dash arrow — every consumer surface uses the same fallback so
 * partial data renders consistently with the rest of the legend.
 */

/**
 * Level identifier. The user's spec specified the simplified-Chinese
 * spelling in the public API contract — keeping it byte-for-byte so
 * external callers / fixtures keying off the string don't drift.
 */
export type SentimentLevel = "过热" | "上涨" | "平" | "下跌" | "深跌";

/** Display label in Traditional Chinese — what the UI actually shows. */
export type SentimentLabel = "過熱" | "上漲" | "平" | "下跌" | "深跌";

export interface SentimentClassification {
  /** Canonical level identifier (Simplified Chinese, per spec). */
  level: SentimentLevel;
  /** Traditional-Chinese label suitable for UI display. */
  label: SentimentLabel;
  /** Emoji prefix used in dense rows / cell badges. */
  emoji: "🔴" | "🟠" | "⚪" | "🔵" | "🟣";
  /** Tailwind text-* class for foreground colour. */
  colorClass:
    | "text-red-400"
    | "text-orange-400"
    | "text-gray-400"
    | "text-sky-400"
    | "text-purple-400";
  /** Tailwind bg-* class for heatmap-style fills. */
  bgClass:
    | "bg-red-500/80"
    | "bg-orange-500/60"
    | "bg-gray-500/30"
    | "bg-sky-500/60"
    | "bg-purple-500/80";
  /** Direction glyph aligned with the level. */
  arrow: "▲" | "▼" | "—";
}

const HEATED_THRESHOLD = 1;
const FLAT_BAND = 0.1;
const DEEP_DROP_THRESHOLD = -1;

const HEATED: SentimentClassification = {
  level: "过热",
  label: "過熱",
  emoji: "🔴",
  colorClass: "text-red-400",
  bgClass: "bg-red-500/80",
  arrow: "▲",
};
const UP: SentimentClassification = {
  level: "上涨",
  label: "上漲",
  emoji: "🟠",
  colorClass: "text-orange-400",
  bgClass: "bg-orange-500/60",
  arrow: "▲",
};
const FLAT: SentimentClassification = {
  level: "平",
  label: "平",
  emoji: "⚪",
  colorClass: "text-gray-400",
  bgClass: "bg-gray-500/30",
  arrow: "—",
};
const DOWN: SentimentClassification = {
  level: "下跌",
  label: "下跌",
  emoji: "🔵",
  colorClass: "text-sky-400",
  bgClass: "bg-sky-500/60",
  arrow: "▼",
};
const DEEP_DROP: SentimentClassification = {
  level: "深跌",
  label: "深跌",
  emoji: "🟣",
  colorClass: "text-purple-400",
  bgClass: "bg-purple-500/80",
  arrow: "▼",
};

/**
 * Classify a percent-change value into the 5-level sentiment band.
 *
 * `changePercent` is interpreted as a percentage, NOT a fraction.
 * Pass `-1.23` to mean "-1.23 %", not `-0.0123`.
 *
 * `null`, `undefined`, `NaN`, and non-finite numbers collapse to "平" —
 * callers don't need a separate fallback path.
 */
export function classifySentiment(
  changePercent: number | string | null | undefined,
): SentimentClassification {
  if (changePercent === null || changePercent === undefined || changePercent === "") {
    return FLAT;
  }
  const n =
    typeof changePercent === "number" ? changePercent : Number(changePercent);
  if (!Number.isFinite(n)) return FLAT;

  if (n >= HEATED_THRESHOLD) return HEATED;
  if (n >= FLAT_BAND) return UP;
  if (n <= DEEP_DROP_THRESHOLD) return DEEP_DROP;
  if (n <= -FLAT_BAND) return DOWN;
  return FLAT;
}
