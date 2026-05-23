"use client";

/**
 * Holdings KPI Row — KPIs mapped from either a `HoldingSummary`
 * (legacy single-currency) or a `MultiCurrencyHoldingSummary` (Round 10
 * Z1). The discriminator is `'by_currency' in summary`, exported as a
 * type guard from `@/lib/api-client`.
 *
 * Single-currency mode: 5 cards. Multi-currency mode: 6 cards — the
 * extra one is "幣別分布" (currency breakdown) rendered as a stacked-
 * percentage mini bar based on `total_value_in_base`.
 *
 * Owns no state; pure presentational. When `loading` is true OR
 * `summary` is undefined, skeletons are rendered so the layout
 * never jumps when data arrives.
 */
import React from "react";
import { KpiCard } from "@/components/stratos/primitives";
import {
  isMultiCurrencyHoldingSummary,
  type HoldingSummary,
  type MultiCurrencyHoldingSummary,
} from "@/lib/api-client";
import {
  toNumber,
  fmt,
  fmtSigned,
  pnlDirection,
} from "./types";
import { CURRENCY_SYMBOL } from "./currency-switcher";
import type { Currency } from "@/lib/api-client";

export interface HoldingsKpiRowProps {
  summary: HoldingSummary | MultiCurrencyHoldingSummary | undefined;
  loading?: boolean;
  /**
   * Optional override for the currency symbol prefix shown on each
   * KPI value. When omitted we derive it from `summary.base_currency`
   * (multi-currency mode) or fall back to "TWD".
   */
  displayCurrency?: Currency;
  /** i18n label for the new 6th KPI in multi-currency mode. */
  byCurrencyLabel?: string;
}

/* ------------------------------------------------------------------ */
/*  Skeleton tile — same outer chrome as KpiCard for layout stability  */
/* ------------------------------------------------------------------ */

function KpiSkeleton() {
  return (
    <div
      style={{
        background: "var(--glass-bg)",
        backdropFilter: "var(--glass-blur)",
        WebkitBackdropFilter: "var(--glass-blur)",
        border: "1px solid var(--border-color)",
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        padding: 20,
      }}
    >
      <div
        style={{
          width: "55%",
          height: 11,
          background: "var(--card-hover)",
          marginBottom: 8,
        }}
      />
      <div
        style={{
          width: "80%",
          height: 28,
          background: "var(--card-hover)",
          marginBottom: 8,
        }}
      />
      <div
        style={{
          width: "40%",
          height: 12,
          background: "var(--card-hover)",
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Currency breakdown KPI tile (6th in multi mode)                    */
/* ------------------------------------------------------------------ */

interface CurrencyShareRow {
  currency: string;
  pct: number;
  valueInBase: number;
}

interface CurrencyBreakdownKpiProps {
  label: string;
  rows: CurrencyShareRow[];
  baseSymbol: string;
}

// Distinct, accessible-contrast palette pulled from STRATOS tokens.
// We DON'T pull --stock-up / --stock-down because those map to P&L
// semantics and would lie about magnitude here.
const CCY_COLORS: string[] = [
  "var(--accent-cyan)",
  "var(--accent-primary)",
  "var(--text-secondary)",
  "#a78bfa", // violet
  "#fbbf24", // amber
  "#34d399", // green
  "#f87171", // red
];

function CurrencyBreakdownKpi({
  label,
  rows,
  baseSymbol,
}: CurrencyBreakdownKpiProps) {
  if (rows.length === 0) {
    return (
      <div
        style={{
          background: "var(--glass-bg)",
          backdropFilter: "var(--glass-blur)",
          WebkitBackdropFilter: "var(--glass-blur)",
          border: "1px solid var(--border-color)",
          backgroundImage: "var(--glass-gradient)",
          boxShadow: "var(--glass-shadow)",
          borderRadius: "var(--glass-radius, 0)",
          padding: 20,
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: "var(--text-secondary)",
            marginBottom: 4,
          }}
        >
          {label}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>—</div>
      </div>
    );
  }
  return (
    <div
      style={{
        background: "var(--glass-bg)",
        backdropFilter: "var(--glass-blur)",
        WebkitBackdropFilter: "var(--glass-blur)",
        border: "1px solid var(--border-color)",
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--text-secondary)",
        }}
      >
        {label}
      </div>
      {/* Stacked horizontal bar */}
      <div
        role="img"
        aria-label={rows
          .map((r) => `${r.currency} ${r.pct.toFixed(1)}%`)
          .join(", ")}
        style={{
          display: "flex",
          height: 8,
          width: "100%",
          overflow: "hidden",
          border: "1px solid var(--border-color)",
        }}
      >
        {rows.map((r, i) => (
          <div
            key={r.currency}
            style={{
              width: `${r.pct}%`,
              background: CCY_COLORS[i % CCY_COLORS.length],
            }}
            title={`${r.currency} ${r.pct.toFixed(1)}%`}
          />
        ))}
      </div>
      {/* Legend rows */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 3,
          fontSize: 11,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {rows.slice(0, 4).map((r, i) => (
          <div
            key={r.currency}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              color: "var(--foreground)",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                background: CCY_COLORS[i % CCY_COLORS.length],
              }}
            />
            <span style={{ fontWeight: 600 }}>{r.currency}</span>
            <span style={{ color: "var(--text-muted)" }}>
              {r.pct.toFixed(1)}%
            </span>
          </div>
        ))}
        {rows.length > 4 && (
          <div style={{ color: "var(--text-muted)" }}>
            +{rows.length - 4} more
          </div>
        )}
      </div>
      <div
        style={{
          fontSize: 10,
          color: "var(--text-muted)",
          marginTop: 2,
        }}
      >
        in {baseSymbol}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function HoldingsKpiRow({
  summary,
  loading = false,
  displayCurrency,
  byCurrencyLabel = "幣別分布",
}: HoldingsKpiRowProps) {
  const isMulti = summary ? isMultiCurrencyHoldingSummary(summary) : false;
  const columnCount = isMulti ? 6 : 5;

  // We DON'T put gridTemplateColumns in a static const because the
  // column count flips between 5 and 6 between renders. Build inline.
  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
    gap: 12,
  };
  const responsiveGridClass =
    columnCount === 6
      ? "grid-cols-2 md:grid-cols-3 xl:grid-cols-6"
      : "grid-cols-2 md:grid-cols-5";

  // Skeleton path — loading OR data not yet fetched
  if (loading || !summary) {
    return (
      <div style={gridStyle} className={responsiveGridClass}>
        {Array.from({ length: columnCount }).map((_, i) => (
          <KpiSkeleton key={i} />
        ))}
      </div>
    );
  }

  // Convert all decimal-strings up front — single source of truth.
  // In multi-currency mode the values are already expressed in
  // `base_currency`, so the same calculations apply.
  const totalValue = toNumber(summary.total_value) ?? 0;
  const totalCost = toNumber(summary.total_cost) ?? 0;
  const unrealizedPnl = toNumber(summary.total_unrealized_pnl) ?? 0;
  const dailyChange = toNumber(summary.total_daily_change) ?? 0;
  const gainPct = toNumber(summary.gain_simple_pct) ?? 0;

  const gainPctStr = `${gainPct >= 0 ? "+" : ""}${gainPct.toFixed(2)}%`;

  // Pick the symbol to prefix on each KPI value.
  const baseCcy: Currency =
    displayCurrency ??
    (isMulti
      ? (((summary as MultiCurrencyHoldingSummary).base_currency as Currency) ??
        "TWD")
      : "TWD");
  const symbol = CURRENCY_SYMBOL[baseCcy] ?? "";

  // Build the rows for the 6th KPI (multi mode only).
  let breakdownRows: CurrencyShareRow[] = [];
  if (isMulti) {
    const multi = summary as MultiCurrencyHoldingSummary;
    const denom = totalValue !== 0 ? totalValue : 1;
    breakdownRows = multi.by_currency
      .map((b) => {
        const valueInBase = toNumber(b.total_value_in_base) ?? 0;
        return {
          currency: b.currency,
          valueInBase,
          pct: (valueInBase / denom) * 100,
        };
      })
      .sort((a, b) => b.pct - a.pct);
  }

  return (
    <div style={gridStyle} className={responsiveGridClass}>
      <KpiCard
        label="總市值"
        value={`${symbol} ${fmt(totalValue, 0)}`}
        delta={baseCcy}
        direction="flat"
      />
      <KpiCard
        label="總成本"
        value={`${symbol} ${fmt(totalCost, 0)}`}
        delta={`${summary.position_count} 檔 · ${summary.account_count} 戶`}
        direction="flat"
      />
      <KpiCard
        label="未實現損益"
        value={`${symbol} ${fmtSigned(unrealizedPnl, 0)}`}
        delta={gainPctStr}
        direction={pnlDirection(unrealizedPnl)}
      />
      <KpiCard
        label="今日漲跌"
        value={`${symbol} ${fmtSigned(dailyChange, 0)}`}
        delta={
          totalValue > 0
            ? `${((dailyChange / totalValue) * 100).toFixed(2)}%`
            : "—"
        }
        direction={pnlDirection(dailyChange)}
      />
      <KpiCard
        label="持股檔數"
        value={String(summary.position_count)}
        delta={`${summary.account_count} 個帳戶`}
        direction="flat"
      />
      {isMulti && (
        <CurrencyBreakdownKpi
          label={byCurrencyLabel}
          rows={breakdownRows}
          baseSymbol={baseCcy}
        />
      )}
    </div>
  );
}
