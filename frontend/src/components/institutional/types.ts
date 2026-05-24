/**
 * Institutional 13F — frontend helpers.
 *
 * Decimal-as-string conversion + display formatters shared across the
 * filer list, holdings table, diff view, and refresh button. Mirrors the
 * shape of `components/holdings/types.ts`, but adds 13F-specific helpers:
 *
 *   - `fmtCompact` — abbreviates large USD values (e.g. "$1.5M" / "$55B"),
 *     because 13F market values frequently break the $1B mark and a flat
 *     thousands-separated string is unreadable.
 *   - `changeTypeColor` / `changeTypeLabel` — single source of truth for
 *     the 5-way diff classification, so DiffView and per-row badges agree.
 *
 * Color convention: TAIWAN/CN (see CLAUDE.md), where RED is "up" / NEW /
 * INCREASED and GREEN is "down" / DECREASED / EXITED — opposite of the US
 * convention. We delegate to CSS custom properties `--stock-up` /
 * `--stock-down` so theme switching adapts both polarities at once.
 */

import type {
  F13ChangeType,
  F13Filer,
  F13Filing,
  F13Holding,
  F13HoldingChange,
} from "@/lib/api-client";

// Re-export the wire types so component files import everything from one place.
export type {
  F13Filer,
  F13Filing,
  F13Holding,
  F13HoldingChange,
  F13ChangeType,
};

/**
 * Decimal-string → number.
 *
 * Backend numeric columns (USD values, share counts, deltas) are emitted
 * as JSON strings. `null` propagates so callers render an em-dash.
 */
export function toDecimal(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * Compact USD formatter — "$1.5M" / "$55B" style.
 *
 * Picks the scale based on magnitude. Returns "—" for null/NaN. The result
 * is intentionally locale-neutral (no thousand separator inside the
 * mantissa) so 13F's USD-only domain stays unambiguous.
 */
export function fmtCompact(
  n: number | null | undefined,
  withDollarSign = true,
): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  const prefix = withDollarSign ? "$" : "";

  if (abs >= 1e12) return `${sign}${prefix}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${prefix}${abs.toFixed(0)}`;
}

/** Locale-aware integer formatter — share counts, position counts, etc. */
export function fmtInt(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/**
 * Signed percentage formatter — "+12.3%" / "-12.3%" / "—".
 *
 * Backend `delta_pct` is already a percent value (e.g. "12.34" means
 * +12.34%); we add the sign + suffix.
 */
export function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const body = `${Math.abs(n).toFixed(2)}%`;
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

/**
 * Map a change_type to a color CSS custom property.
 *
 * TAIWAN convention (CLAUDE.md): NEW / INCREASED are bullish → red;
 * DECREASED / EXITED are bearish → green; UNCHANGED is muted.
 */
export function changeTypeColor(
  changeType: F13ChangeType | string,
): string {
  switch (changeType) {
    case "NEW":
    case "INCREASED":
      return "var(--stock-up)";
    case "DECREASED":
    case "EXITED":
      return "var(--stock-down)";
    case "UNCHANGED":
    default:
      return "var(--text-muted)";
  }
}

/** zh-TW label for a change_type. */
export function changeTypeLabel(
  changeType: F13ChangeType | string,
): string {
  switch (changeType) {
    case "NEW":
      return "新增";
    case "INCREASED":
      return "加碼";
    case "DECREASED":
      return "減碼";
    case "EXITED":
      return "清倉";
    case "UNCHANGED":
      return "持平";
    default:
      return changeType;
  }
}

/** Short symbol-ish display for a holding — symbol if mapped, CUSIP else. */
export function holdingDisplaySymbol(h: F13Holding): string {
  return h.stock_symbol ?? h.cusip;
}
