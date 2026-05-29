"use client";

/**
 * QuoteRow — canonical stock-listing row.
 *
 * Renders the full ID-set the user requested:
 *   symbol + name + price + absolute change + percent change
 *
 * Used by Market Movers (home), heatmap detail rows, command-palette
 * search results, and any future stock-list surface. Two variants:
 *
 * - `default` — two-line layout (symbol on top, name below); price &
 *   change stacked on the right. Used by lists with vertical room.
 * - `compact` — single-line layout. Used by ticker strips / dense
 *   embedded lists (e.g. heatmap sector cell expansion).
 *
 * Field gaps are rendered as an em-dash ("—") rather than hidden or
 * zero-filled, so the user can see at a glance which API surfaces
 * still need backend work (search, signal scanner).
 */

import Link from "next/link";
import React from "react";

export type QuoteRowVariant = "default" | "compact";

export interface QuoteRowProps {
  symbol: string;
  /** Display name (e.g. "聯發科"). When undefined/empty, renders an em-dash. */
  name?: string | null;
  /**
   * Last price as a string or number. The backend hands prices back as
   * strings (Decimal-as-string contract) — we accept both shapes and
   * normalise internally. `null`/`undefined` means "no price data
   * available from this surface yet" and renders as "—".
   */
  price?: string | number | null;
  /**
   * Absolute change. Optional — when not supplied but `price` and
   * `changePercent` are both known, we derive it (change ≈ price ×
   * percent / 100). When neither input is available, renders "—".
   */
  change?: string | number | null;
  /** Percent change, e.g. -1.23 for -1.23 %. */
  changePercent?: string | number | null;
  /** Optional market label (e.g. "TWSE", "NASDAQ") shown as a chip. */
  market?: string | null;
  /** When truthy, wrap the row in a Next.js Link to /stocks/[symbol]. */
  href?: string;
  /** Row variant — see file header. */
  variant?: QuoteRowVariant;
  /** Rank index (1-based) shown to the left in `default` variant. */
  rank?: number;
  /** Click handler used in place of `href`. */
  onClick?: () => void;
  /** Extra class on the row's outer element. */
  className?: string;
  /** ARIA role applied to the row (e.g. "option" for combobox results). */
  role?: string;
  /** ARIA aria-selected — used by command-palette to mark active result. */
  ariaSelected?: boolean;
  /** Inline style applied to the row's outer element (escape hatch). */
  style?: React.CSSProperties;
  /** Arbitrary data-* attributes (e.g. data-result-item for query selectors). */
  dataAttributes?: Record<string, string | number | boolean | undefined>;
}

const DASH = "—";

/** Strip TW market suffixes for display while keeping the original for routing. */
function displaySymbol(symbol: string): string {
  return symbol.replace(/\.TW$|\.TWO$/, "");
}

function shortMarket(market: string | null | undefined): string | null {
  if (!market) return null;
  if (market.startsWith("TW_TWSE")) return "TWSE";
  if (market.startsWith("TW_TPEX")) return "TPEX";
  if (market.includes("NASDAQ")) return "NASDAQ";
  if (market.includes("NYSE")) return "NYSE";
  return market;
}

function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function formatPrice(n: number): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatSignedFixed(n: number): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}`;
}

interface RowAnchorProps {
  href?: string;
  onClick?: () => void;
  className?: string;
  role?: string;
  ariaSelected?: boolean;
  style?: React.CSSProperties;
  dataAttributes?: Record<string, string | number | boolean | undefined>;
  children: React.ReactNode;
}

/** Renders as a Link, button, or plain div depending on what's provided. */
function RowAnchor({
  href,
  onClick,
  className,
  role,
  ariaSelected,
  style,
  dataAttributes,
  children,
}: RowAnchorProps) {
  // Spread data-* attributes onto the rendered element. React doesn't
  // accept arbitrary keys via props so we hand-roll the mapping.
  const dataProps: Record<string, string | number | boolean> = {};
  if (dataAttributes) {
    for (const [k, v] of Object.entries(dataAttributes)) {
      if (v === undefined) continue;
      dataProps[k] = v;
    }
  }
  const common = {
    className,
    role,
    "aria-selected": ariaSelected,
    style,
    ...dataProps,
  } as const;

  if (href) {
    return (
      <Link href={href} onClick={onClick} {...common}>
        {children}
      </Link>
    );
  }
  if (onClick) {
    return (
      <button type="button" onClick={onClick} {...common}>
        {children}
      </button>
    );
  }
  return <div {...common}>{children}</div>;
}

export function QuoteRow({
  symbol,
  name,
  price,
  change,
  changePercent,
  market,
  href,
  variant = "default",
  rank,
  onClick,
  className,
  role,
  ariaSelected,
  style,
  dataAttributes,
}: QuoteRowProps) {
  const priceNum = toNum(price);
  const pctNum = toNum(changePercent);
  let changeNum = toNum(change);

  // Derive absolute change when missing but both price and pct are known.
  // Mirrors the backend's own convention so the user sees a consistent
  // number regardless of which API surface served the row.
  if (changeNum === null && priceNum !== null && pctNum !== null) {
    changeNum = (priceNum * pctNum) / 100;
  }

  // Direction lock-step: pct drives the colour. If only abs change is
  // known, fall back to that. Otherwise neutral.
  const directionSource = pctNum ?? changeNum ?? 0;
  const isUp = directionSource > 0;
  const isDown = directionSource < 0;
  const colorVar = isUp
    ? "var(--stock-up)"
    : isDown
      ? "var(--stock-down)"
      : "var(--text-muted)";

  const priceText = priceNum !== null ? formatPrice(priceNum) : DASH;
  const changeText = changeNum !== null ? formatSignedFixed(changeNum) : DASH;
  const pctText = pctNum !== null ? `${formatSignedFixed(pctNum)}%` : DASH;
  const displayName = name && name.trim() ? name : DASH;
  const marketChip = shortMarket(market);
  const sym = displaySymbol(symbol);

  if (variant === "compact") {
    // One-line dense row — used in ticker strips and inside heatmap
    // sector cells. Keeps every field but trims separators.
    const rootClass = [
      "flex items-center gap-2 px-2 py-1 text-[11px] font-mono",
      "hover:bg-[var(--card-hover)] transition-colors text-left w-full",
      className ?? "",
    ].join(" ");
    return (
      <RowAnchor
        href={href}
        onClick={onClick}
        className={rootClass}
        role={role}
        ariaSelected={ariaSelected}
        style={style}
        dataAttributes={dataAttributes}
      >
        <span className="font-bold text-[var(--foreground)] tabular-nums shrink-0">
          {sym}
        </span>
        <span className="text-[var(--text-secondary)] truncate flex-1 min-w-0">
          {displayName}
        </span>
        <span className="tabular-nums text-[var(--foreground)] shrink-0">
          {priceText}
        </span>
        <span
          className="tabular-nums font-bold shrink-0"
          style={{ color: colorVar }}
        >
          {changeText}
        </span>
        <span
          className="tabular-nums font-bold shrink-0"
          style={{ color: colorVar }}
        >
          {pctText}
        </span>
      </RowAnchor>
    );
  }

  // default — two-line layout, used by ranked lists with room.
  const rootClass = [
    "flex items-center gap-3 px-2 py-2 text-left w-full",
    "border-b border-[rgba(255,255,255,0.04)] last:border-b-0",
    "hover:bg-[var(--card-hover)] transition-colors",
    className ?? "",
  ].join(" ");

  return (
    <RowAnchor href={href} onClick={onClick} className={rootClass}>
      {rank !== undefined && (
        <span className="text-[10px] text-[var(--text-muted)] tabular-nums w-5 text-right shrink-0">
          {rank}
        </span>
      )}
      <div className="flex flex-col min-w-0 flex-1">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[13px] font-bold text-[var(--foreground)] tabular-nums shrink-0">
            {sym}
          </span>
          {marketChip && (
            <span className="text-[9px] text-[var(--text-muted)] px-1 py-px border border-[var(--border-color)] rounded shrink-0 uppercase tracking-wider">
              {marketChip}
            </span>
          )}
        </div>
        <span className="text-[11px] text-[var(--text-secondary)] truncate">
          {displayName}
        </span>
      </div>
      <div className="flex flex-col items-end shrink-0">
        <span className="text-[13px] tabular-nums text-[var(--foreground)] font-semibold">
          {priceText}
        </span>
        <span
          className="text-[11px] tabular-nums font-semibold"
          style={{ color: colorVar }}
        >
          {changeText} ({pctText})
        </span>
      </div>
    </RowAnchor>
  );
}

export default QuoteRow;
