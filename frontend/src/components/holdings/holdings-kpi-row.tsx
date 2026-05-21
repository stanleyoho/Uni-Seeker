"use client";

/**
 * Holdings KPI Row — 5 KpiCards mapped from a HoldingSummary.
 *
 * Owns no state; pure presentational. When `loading` is true OR
 * `summary` is undefined, skeletons are rendered so the layout
 * never jumps when data arrives.
 */
import React from "react";
import { KpiCard } from "@/components/stratos/primitives";
import {
  type HoldingSummary,
  toNumber,
  fmt,
  fmtSigned,
  pnlDirection,
} from "./types";

export interface HoldingsKpiRowProps {
  summary: HoldingSummary | undefined;
  loading?: boolean;
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
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
  gap: 12,
};

const gridResponsive: React.CSSProperties = {
  ...gridStyle,
};

export function HoldingsKpiRow({ summary, loading = false }: HoldingsKpiRowProps) {
  // Skeleton path — loading OR data not yet fetched
  if (loading || !summary) {
    return (
      <div style={gridResponsive} className="grid-cols-2 md:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <KpiSkeleton key={i} />
        ))}
      </div>
    );
  }

  // Convert all decimal-strings up front — single source of truth
  const totalValue = toNumber(summary.total_value) ?? 0;
  const totalCost = toNumber(summary.total_cost) ?? 0;
  const unrealizedPnl = toNumber(summary.total_unrealized_pnl) ?? 0;
  const dailyChange = toNumber(summary.total_daily_change) ?? 0;
  const gainPct = toNumber(summary.gain_simple_pct) ?? 0;

  // gain_simple_pct from backend is already a percent (e.g. "12.34"
  // means +12.34%). If backend swaps to a 0..1 ratio, multiply here.
  const gainPctStr = `${gainPct >= 0 ? "+" : ""}${gainPct.toFixed(2)}%`;

  return (
    <div style={gridResponsive} className="grid-cols-2 md:grid-cols-5">
      <KpiCard
        label="總市值"
        value={fmt(totalValue, 0)}
        delta={summary.currency_hint ?? "TWD"}
        direction="flat"
      />
      <KpiCard
        label="總成本"
        value={fmt(totalCost, 0)}
        delta={`${summary.position_count} 檔 · ${summary.account_count} 戶`}
        direction="flat"
      />
      <KpiCard
        label="未實現損益"
        value={fmtSigned(unrealizedPnl, 0)}
        delta={gainPctStr}
        direction={pnlDirection(unrealizedPnl)}
      />
      <KpiCard
        label="今日漲跌"
        value={fmtSigned(dailyChange, 0)}
        delta={totalValue > 0
          ? `${((dailyChange / totalValue) * 100).toFixed(2)}%`
          : "—"}
        direction={pnlDirection(dailyChange)}
      />
      <KpiCard
        label="持股檔數"
        value={String(summary.position_count)}
        delta={`${summary.account_count} 個帳戶`}
        direction="flat"
      />
    </div>
  );
}

/* Augmentation: `currency_hint` is optional, included only if a
   future backend revision attaches a display currency to summary. The
   property is referenced via index access so TS does not flag the
   missing field — it stays undefined for current SummaryResponse. */
declare module "./types" {
  interface HoldingSummary {
    currency_hint?: string;
  }
}
