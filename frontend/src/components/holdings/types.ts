/**
 * Holdings — frontend type contracts.
 *
 * These mirror the backend `app/schemas/holdings/*.py` wire shapes
 * (Decimal-as-string, §7 spec). Once `src/lib/api-client.ts` grows
 * dedicated holdings endpoints these interfaces should be moved there
 * and re-exported from this module for backwards compatibility.
 *
 * Backend field-name authority — `PositionResponse.qty` (NOT `quantity`).
 * If the wire format renames, update here in one place.
 */

export type HoldingMarket =
  | "TW_TWSE"
  | "TW_TPEX"
  | "US_NYSE"
  | "US_NASDAQ"
  | "CRYPTO"
  | string;

export interface HoldingAccount {
  id: number;
  name: string;
  market: HoldingMarket;
  broker: string | null;
  currency: string;
  description: string | null;
  created_at: string;
}

export interface HoldingPosition {
  account_id: number;
  symbol: string;
  market: HoldingMarket;
  currency: string;
  /** Decimal-as-string. Convert with `Number(qty)` before arithmetic. */
  qty: string;
  avg_cost: string | null;
  total_cost: string | null;
  realized_pnl: string;
  last_price: string | null;
  prev_close: string | null;
  price_as_of: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_pct: string | null;
  daily_change: string | null;
  daily_change_pct: string | null;
  is_closed: boolean;
}

export interface HoldingSummary {
  total_cost: string;
  total_value: string;
  total_unrealized_pnl: string;
  total_daily_change: string;
  gain_simple: string;
  gain_simple_pct: string;
  position_count: number;
  account_count: number;
}

/**
 * Shared decimal-string → number helper.
 *
 * Decimal-as-string contract (CLAUDE.md frontend rule): backend numeric
 * fields land as `string`; never do arithmetic on them directly.
 * `null` propagates as `null` so callers can render an em-dash.
 */
export function toNumber(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * Locale-aware formatter — thousand separator + fixed decimals.
 * Returns the em-dash placeholder when `n` is null/undefined.
 */
export function fmt(n: number | null | undefined, decimals = 0): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Sign-prefixed format ("+1,234" / "-1,234" / "—"). */
export function fmtSigned(n: number | null | undefined, decimals = 0): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const body = fmt(Math.abs(n), decimals);
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

/** Color resolver for P&L cells. */
export function pnlColor(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return "var(--foreground)";
  return n > 0 ? "var(--stock-up)" : "var(--stock-down)";
}

/** Direction resolver for KpiCard arrow. */
export function pnlDirection(n: number | null | undefined): "up" | "down" | "flat" {
  if (n == null || !Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}
