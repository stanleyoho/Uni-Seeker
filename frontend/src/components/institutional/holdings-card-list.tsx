"use client";

/**
 * Institutional Holdings Card List — Phase 7 mobile-first redesign.
 *
 * Mobile alternative for `institutional/holdings-table.tsx`. Same props
 * (`InstitutionalHoldingsTableProps`); each row of a filer's 13F lands
 * as a vertical card:
 *
 *   ┌──────────────────────────────────────────────┐
 *   │ NVDA  [NASDAQ]                          PUT  │  ← top: symbol/CUSIP + market badge + put/call
 *   │ NVIDIA CORP                                  │  ← issuer (full text, wraps)
 *   │ Shares 1.2M    Value $1.5B (12.5%)           │  ← shares + value/pct
 *   │ Discretion SOLE                              │  ← discretion footer (when present)
 *   └──────────────────────────────────────────────┘
 *
 * Notes:
 *   - 13F is US-only — no MarketBadge here (there's no equivalent market
 *     code on `F13Holding`); the put/call badge is the primary chip.
 *   - Long issuer names (e.g. "TESLA INC COM PAR VALUE 0.001") wrap to
 *     two lines and clamp at three via `WebkitLineClamp` so cards stay a
 *     consistent height in the worst case.
 *   - Symbol vs CUSIP fallback handled by `holdingDisplaySymbol()` —
 *     unmapped CUSIPs render in monospace.
 */

import { useMemo } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import {
  fmtCompact,
  fmtInt,
  holdingDisplaySymbol,
  toDecimal,
  type F13Holding,
} from "./types";

export interface InstitutionalHoldingsCardListProps {
  holdings: F13Holding[];
  loading?: boolean;
  onRowClick?: (holding: F13Holding) => void;
}

/* ------------------------------------------------------------------ */
/*  Put/Call badge — shared visual with the desktop table              */
/* ------------------------------------------------------------------ */

function PutCallBadge({ value }: { value: "PUT" | "CALL" | null }) {
  if (!value) return null;
  const color = value === "PUT" ? "var(--stock-down)" : "var(--stock-up)";
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 9,
        fontWeight: 700,
        padding: "2px 6px",
        background: `color-mix(in srgb, ${color} 18%, transparent)`,
        color,
        border: `1px solid ${color}`,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        flexShrink: 0,
      }}
    >
      {value}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--border-subtle)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 96,
      }}
    >
      <div
        style={{
          height: 14,
          background: "var(--card-hover)",
          width: "30%",
        }}
      />
      <div
        style={{
          height: 12,
          background: "var(--card-hover)",
          width: "80%",
        }}
      />
      <div
        style={{
          height: 12,
          background: "var(--card-hover)",
          width: "55%",
        }}
      />
    </div>
  );
}

interface DerivedRow {
  raw: F13Holding;
  shares: number | null;
  value_usd: number;
  pct_of_total: number;
}

export function InstitutionalHoldingsCardList({
  holdings,
  loading = false,
  onRowClick,
}: InstitutionalHoldingsCardListProps) {
  /* Pre-derive numbers + pct-of-portfolio. Sort desc by value (matches
   * the desktop table's default and is what mobile users expect — top
   * holdings first). */
  const { rows, totalValue } = useMemo(() => {
    const noPct: Omit<DerivedRow, "pct_of_total">[] = holdings.map((h) => ({
      raw: h,
      shares: toDecimal(h.shares),
      value_usd: toDecimal(h.value_usd) ?? 0,
    }));
    const total = noPct.reduce((s, r) => s + r.value_usd, 0);
    const withPct: DerivedRow[] = noPct.map((r) => ({
      ...r,
      pct_of_total: total > 0 ? (r.value_usd / total) * 100 : 0,
    }));
    withPct.sort((a, b) => b.value_usd - a.value_usd);
    return { rows: withPct, totalValue: total };
  }, [holdings]);

  if (!loading && rows.length === 0) {
    return (
      <GlassPanel noPadding>
        <div
          style={{
            padding: 24,
            color: "var(--text-muted)",
            fontSize: 13,
            textAlign: "center",
          }}
        >
          此期間無持倉資料 — 試試 refresh 拉最新 13F-HR
        </div>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel noPadding>
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          color: "var(--foreground)",
        }}
      >
        {loading
          ? Array.from({ length: 6 }).map((_, i) => (
              <li key={i}>
                <SkeletonCard />
              </li>
            ))
          : rows.map((r) => {
              const clickable = !!onRowClick;
              const symbolLabel = holdingDisplaySymbol(r.raw);
              return (
                <li
                  key={r.raw.id}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  <div
                    role={clickable ? "button" : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    onClick={clickable ? () => onRowClick(r.raw) : undefined}
                    onKeyDown={(e) => {
                      if (!clickable) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onRowClick(r.raw);
                      }
                    }}
                    style={{
                      padding: "14px 16px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                      cursor: clickable ? "pointer" : "default",
                      minHeight: 96,
                    }}
                  >
                    {/* Top row — symbol/CUSIP + put/call */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        minWidth: 0,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 15,
                          fontWeight: 700,
                          color: "var(--foreground)",
                          fontFamily: r.raw.stock_symbol
                            ? "inherit"
                            : "monospace",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          flex: 1,
                          minWidth: 0,
                        }}
                        title={symbolLabel}
                      >
                        {symbolLabel}
                      </span>
                      <PutCallBadge value={r.raw.put_call} />
                    </div>

                    {/* Issuer — full text, wraps to max 2 lines */}
                    <p
                      style={{
                        margin: 0,
                        fontSize: 11,
                        color: "var(--text-secondary)",
                        lineHeight: 1.4,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                      title={r.raw.name_of_issuer}
                    >
                      {r.raw.name_of_issuer}
                    </p>

                    {/* Shares + Value */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 12,
                        alignItems: "flex-end",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                          minWidth: 0,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--text-muted)",
                          }}
                        >
                          Shares
                        </span>
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 600,
                            fontVariantNumeric: "tabular-nums",
                            color: "var(--foreground)",
                          }}
                        >
                          {fmtInt(r.shares)}
                        </span>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                          alignItems: "flex-end",
                          minWidth: 0,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--text-muted)",
                          }}
                        >
                          Value (USD)
                        </span>
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            fontVariantNumeric: "tabular-nums",
                            color: "var(--foreground)",
                          }}
                        >
                          {fmtCompact(r.value_usd)}
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            color: "var(--text-muted)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {totalValue > 0
                            ? `${r.pct_of_total.toFixed(2)}%`
                            : "—"}
                        </span>
                      </div>
                    </div>

                    {/* Discretion footer (only when present) */}
                    {r.raw.investment_discretion && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 9,
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--text-muted)",
                          }}
                        >
                          Discretion
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            color: "var(--text-secondary)",
                            textTransform: "uppercase",
                            letterSpacing: "0.04em",
                          }}
                        >
                          {r.raw.investment_discretion}
                        </span>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
      </ul>
    </GlassPanel>
  );
}
