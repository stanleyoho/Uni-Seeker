/**
 * STRATOS skeleton primitives.
 *
 * Reserved-shape placeholders used by per-segment `loading.tsx` files
 * (Next 16 Suspense fallback). Goal: zero blank-flash on navigation —
 * the user sees the page's actual layout already locked in, just
 * pulsing with neutral fills instead of data.
 *
 * Design rules:
 *   - Pure server components (no `"use client"`). The fallback must be
 *     server-renderable so Next can stream it instantly.
 *   - No JS — animation is CSS-only via `animate-pulse` (Tailwind).
 *   - Match STRATOS dark-luxe palette: `--glass-bg`, `--border-subtle`,
 *     `--bg-secondary`. No custom colors.
 *   - Sizes mirror the real components (GlassPanel inner padding 24,
 *     KpiCard ≈ 96px tall, QuoteRow ≈ 56px tall).
 */

import React from "react";

const baseBox: React.CSSProperties = {
  background: "var(--bg-secondary, rgba(255,255,255,0.04))",
  border: "1px solid var(--border-subtle, rgba(255,255,255,0.06))",
};

const fillBar: React.CSSProperties = {
  background: "var(--card-hover, rgba(255,255,255,0.08))",
  borderRadius: 2,
};

/**
 * Generic rectangular skeleton block. Width/height controlled by caller
 * (className OR style). Pulses via Tailwind `animate-pulse`.
 */
export function SkeletonBlock({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={`animate-pulse ${className}`}
      style={{ ...fillBar, ...style }}
      aria-hidden="true"
    />
  );
}

/**
 * Mirrors GlassPanel shell — same border / bg / padding so the page
 * layout doesn't shift when the real content swaps in.
 */
export function SkeletonPanel({
  className = "",
  children,
  noPadding = false,
  style,
}: {
  className?: string;
  children?: React.ReactNode;
  noPadding?: boolean;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={className}
      style={{
        ...baseBox,
        padding: noPadding ? 0 : 24,
        ...style,
      }}
      aria-hidden="true"
    >
      {children}
    </div>
  );
}

/**
 * Mirrors KpiCard. 3 stacked rows: label / big number / delta.
 * Caller decides how many to render via `count`.
 */
export function SkeletonKpiRow({ count = 4 }: { count?: number }) {
  return (
    <div
      className={`grid grid-cols-2 lg:grid-cols-${count} gap-4`}
      aria-hidden="true"
    >
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonPanel key={i} className="p-3 lg:p-5" noPadding>
          <div className="p-3 lg:p-5 space-y-2">
            <SkeletonBlock style={{ height: 11, width: "40%" }} />
            <SkeletonBlock style={{ height: 28, width: "70%" }} />
            <SkeletonBlock style={{ height: 12, width: "55%" }} />
          </div>
        </SkeletonPanel>
      ))}
    </div>
  );
}

/**
 * Mirrors QuoteRow stack inside a panel. Used for any list page
 * (low-base, movers, watchlist, holdings).
 */
export function SkeletonQuoteList({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-3 py-3 border-b border-[var(--border-subtle)] last:border-b-0"
        >
          <SkeletonBlock style={{ height: 16, width: 56 }} />
          <SkeletonBlock style={{ height: 16, flex: 1, maxWidth: 200 }} />
          <SkeletonBlock style={{ height: 16, width: 80 }} />
          <SkeletonBlock style={{ height: 16, width: 60 }} />
        </div>
      ))}
    </div>
  );
}

/**
 * Generic page-header skeleton — title + subtitle + optional CTA
 * placeholder on the right. Matches the `<h1>` + meta line nearly every
 * page renders.
 */
export function SkeletonPageHeader({ withCta = true }: { withCta?: boolean }) {
  return (
    <div
      className="flex flex-col md:flex-row md:items-end justify-between mb-8 border-b border-[var(--border-subtle)] pb-4 gap-4"
      aria-hidden="true"
    >
      <div className="space-y-2">
        <SkeletonBlock style={{ height: 32, width: 280 }} />
        <SkeletonBlock style={{ height: 12, width: 200 }} />
      </div>
      {withCta && <SkeletonBlock style={{ height: 36, width: 140 }} />}
    </div>
  );
}

/**
 * Heatmap-style grid — tiles arranged in a responsive grid. Each tile
 * has a header strip + 5 micro-rows (matching SectorBlock).
 */
export function SkeletonTileGrid({ tiles = 8 }: { tiles?: number }) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
      aria-hidden="true"
    >
      {Array.from({ length: tiles }).map((_, i) => (
        <SkeletonPanel key={i} noPadding className="border-t-2 border-[var(--border-subtle)]">
          <div className="p-3 space-y-2">
            <div className="flex items-center justify-between">
              <SkeletonBlock style={{ height: 14, width: "60%" }} />
              <SkeletonBlock style={{ height: 14, width: 50 }} />
            </div>
            <SkeletonBlock style={{ height: 10, width: "30%" }} />
          </div>
          <div className="p-2 space-y-1">
            {Array.from({ length: 5 }).map((_, j) => (
              <div key={j} className="flex items-center justify-between py-1">
                <SkeletonBlock style={{ height: 12, width: 60 }} />
                <SkeletonBlock style={{ height: 12, width: 40 }} />
              </div>
            ))}
          </div>
        </SkeletonPanel>
      ))}
    </div>
  );
}

/**
 * Generic table-shape skeleton — header row + N body rows.
 */
export function SkeletonTable({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <SkeletonPanel noPadding aria-hidden="true">
      <div className="px-4 py-3 border-b border-[var(--border-subtle)] flex gap-3">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonBlock key={i} style={{ height: 12, flex: 1 }} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="px-4 py-3 border-b border-[var(--border-subtle)] last:border-b-0 flex gap-3"
        >
          {Array.from({ length: cols }).map((_, c) => (
            <SkeletonBlock key={c} style={{ height: 16, flex: 1 }} />
          ))}
        </div>
      ))}
    </SkeletonPanel>
  );
}

/**
 * Chart skeleton — tall placeholder with axis-like ticks at the bottom.
 */
export function SkeletonChart({ height = 320 }: { height?: number }) {
  return (
    <SkeletonPanel className="relative overflow-hidden" style={{ height }} aria-hidden="true">
      <div className="absolute inset-6">
        <SkeletonBlock style={{ position: "absolute", inset: 0 }} />
        <div className="absolute bottom-0 left-0 right-0 flex justify-between">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonBlock key={i} style={{ height: 8, width: 30 }} />
          ))}
        </div>
      </div>
    </SkeletonPanel>
  );
}
