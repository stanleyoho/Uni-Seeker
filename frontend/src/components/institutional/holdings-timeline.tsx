"use client";

/**
 * Holdings Timeline — per-stock multi-quarter view for a single filer.
 *
 * Given (filerId, symbolOrCusip) we:
 *   1. Pull the filer's filing list (`useFilings`).
 *   2. Fan-out `getHoldings` calls for each filing via `useQueries` so the
 *      hook count stays stable across renders (React rules-of-hooks). We
 *      cap at MAX_QUARTERS (8) — beyond that the chart gets noisy and the
 *      EDGAR retention story breaks down anyway.
 *   3. For each filing's holdings, find the row matching the requested
 *      symbol or CUSIP. Missing → "未持有" cell.
 *   4. Compose timeline rows in ascending date order, compute QoQ deltas,
 *      and render a sparkline-style bar mini-chart + a table.
 *
 * No new backend endpoint is required; this is a pure composition over
 * existing `/filers/{id}/filings` + `/filers/{id}/holdings` endpoints.
 * Cache keys are (filerId, period) — the same as the snapshot view, so
 * navigation between Timeline and Holdings shares the cache.
 *
 * Color polarity follows the TAIWAN convention via `--stock-up` (red for
 * increases) and `--stock-down` (green for decreases), matching the rest
 * of the institutional UI.
 */

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { GlassPanel } from "@/components/stratos/primitives";
import { getHoldings, type F13HoldingsAtPeriod } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import { useFilings } from "@/hooks/use-institutional";
import {
  fmtCompact,
  fmtInt,
  fmtPct,
  holdingDisplaySymbol,
  toDecimal,
  type F13Holding,
} from "./types";

export interface HoldingsTimelineProps {
  filerId: number;
  /** Symbol (preferred when mapped) or raw CUSIP — matched against both. */
  symbolOrCusip: string;
  /** Optional cap on how many filings to render. Defaults to 8. */
  maxQuarters?: number;
}

interface TimelinePoint {
  period: string;
  shares: number | null;
  valueUsd: number | null;
  /** Holding row pulled from the per-period query, or `null` if not held. */
  holding: F13Holding | null;
  /** Δ shares vs previous period (oldest → newest scan). null on first row. */
  deltaShares: number | null;
  /** Δ value vs previous period. null on first row. */
  deltaValue: number | null;
  /** Δ percent (shares basis) vs previous period. null on first row. */
  deltaPct: number | null;
}

function matchesHolding(h: F13Holding, query: string): boolean {
  const q = query.toUpperCase();
  if (h.stock_symbol && h.stock_symbol.toUpperCase() === q) return true;
  if (h.cusip.toUpperCase() === q) return true;
  return false;
}

/* ----------------------------- Sparkline ----------------------------- */

interface SparklineProps {
  points: TimelinePoint[];
  metric: "shares" | "valueUsd";
  height?: number;
}

function Sparkline({ points, metric, height = 56 }: SparklineProps) {
  const values = points.map((p) =>
    metric === "shares" ? p.shares : p.valueUsd,
  );
  const nonNull = values.filter((v): v is number => v != null && v > 0);

  if (nonNull.length === 0) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        無資料
      </div>
    );
  }

  const max = Math.max(...nonNull);
  const barCount = values.length;
  const gap = 4;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap,
        height,
        padding: "4px 0",
      }}
    >
      {values.map((v, i) => {
        const ratio = v != null && v > 0 ? v / max : 0;
        const barHeight = Math.max(2, ratio * (height - 8));
        const isHeld = v != null && v > 0;
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: barHeight,
              minWidth: 6,
              background: isHeld
                ? "var(--accent-cyan)"
                : "var(--border-subtle)",
              opacity: isHeld ? 0.8 : 0.4,
              transition: "opacity 0.15s",
            }}
            title={`${points[i].period}: ${
              metric === "shares"
                ? fmtInt(points[i].shares)
                : fmtCompact(points[i].valueUsd)
            }`}
          />
        );
      })}
    </div>
  );
}

/* ----------------------------- Status pill ---------------------------- */

function StatusCell({
  point,
  isFirst,
}: {
  point: TimelinePoint;
  isFirst: boolean;
}) {
  if (point.holding == null) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>未持有</span>
    );
  }
  // First row: only label as "持有" since there's no prior period to diff.
  if (isFirst) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>持有</span>
    );
  }
  if (point.deltaShares == null) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>—</span>
    );
  }
  if (point.deltaShares > 0) {
    return (
      <span style={{ fontSize: 11, color: "var(--stock-up)", fontWeight: 600 }}>
        加碼
      </span>
    );
  }
  if (point.deltaShares < 0) {
    if (point.shares === 0 || point.shares == null) {
      return (
        <span
          style={{ fontSize: 11, color: "var(--stock-down)", fontWeight: 600 }}
        >
          已清倉
        </span>
      );
    }
    return (
      <span
        style={{ fontSize: 11, color: "var(--stock-down)", fontWeight: 600 }}
      >
        減碼
      </span>
    );
  }
  return (
    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>持平</span>
  );
}

/* ------------------------------- Main -------------------------------- */

export function HoldingsTimeline({
  filerId,
  symbolOrCusip,
  maxQuarters = 8,
}: HoldingsTimelineProps) {
  const { data: filings = [], isLoading: filingsLoading } = useFilings(filerId);

  /* Trim to the most recent N filings (the API returns newest-first). */
  const tracked = useMemo(
    () => filings.slice(0, maxQuarters),
    [filings, maxQuarters],
  );

  /* Fan-out one holdings query per filing. `useQueries` keeps the hook
   * count constant across renders for a stable `tracked` length. */
  const holdingsQueries = useQueries({
    queries: tracked.map((f) => ({
      queryKey: queryKeys.institutional.filings.holdings(
        filerId,
        f.report_period_end,
      ),
      queryFn: (): Promise<F13HoldingsAtPeriod> =>
        getHoldings(filerId, f.report_period_end),
      enabled: filerId > 0 && symbolOrCusip.length > 0,
      staleTime: 60 * 1000,
    })),
  });

  const someLoading = holdingsQueries.some((q) => q.isLoading);
  const allLoading = holdingsQueries.length > 0 && holdingsQueries.every((q) => q.isLoading);

  /* Compose timeline rows in ascending order (oldest → newest). The diff
   * is meaningful only after we have at least two consecutive points. */
  const points = useMemo<TimelinePoint[]>(() => {
    const asc = [...tracked].reverse();
    const rawPoints: TimelinePoint[] = asc.map((filing) => {
      const queryIndex = tracked.findIndex((f) => f.id === filing.id);
      const res = queryIndex >= 0 ? holdingsQueries[queryIndex]?.data : null;
      const match = res?.holdings.find((h) => matchesHolding(h, symbolOrCusip));
      const shares = match ? toDecimal(match.shares) : null;
      const value = match ? toDecimal(match.value_usd) : null;
      return {
        period: filing.report_period_end,
        shares,
        valueUsd: value,
        holding: match ?? null,
        deltaShares: null,
        deltaValue: null,
        deltaPct: null,
      };
    });

    /* Second pass: compute deltas vs previous point. */
    for (let i = 1; i < rawPoints.length; i++) {
      const prev = rawPoints[i - 1];
      const curr = rawPoints[i];
      const prevShares = prev.shares ?? 0;
      const currShares = curr.shares ?? 0;
      const prevValue = prev.valueUsd ?? 0;
      const currValue = curr.valueUsd ?? 0;
      curr.deltaShares = currShares - prevShares;
      curr.deltaValue = currValue - prevValue;
      curr.deltaPct =
        prevShares > 0 ? ((currShares - prevShares) / prevShares) * 100 : null;
    }

    return rawPoints;
  }, [tracked, holdingsQueries, symbolOrCusip]);

  const displaySymbol = useMemo(() => {
    for (const p of points) {
      if (p.holding) return holdingDisplaySymbol(p.holding);
    }
    return symbolOrCusip;
  }, [points, symbolOrCusip]);

  /* --------------------------- Render --------------------------- */

  if (filingsLoading || allLoading) {
    return (
      <GlassPanel>
        <p
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            textAlign: "center",
            padding: "20px 0",
          }}
        >
          載入中…
        </p>
      </GlassPanel>
    );
  }

  if (tracked.length === 0) {
    return (
      <GlassPanel>
        <p
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            textAlign: "center",
            padding: "20px 0",
          }}
        >
          無 filing — 先點 Refresh 拉取
        </p>
      </GlassPanel>
    );
  }

  const heldCount = points.filter((p) => p.holding != null).length;

  return (
    <GlassPanel noPadding>
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-secondary)",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "baseline",
          gap: 12,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.15em",
            color: "var(--text-muted)",
            textTransform: "uppercase",
          }}
        >
          HOLDINGS TIMELINE
        </span>
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color: "var(--foreground)",
            fontFamily: displaySymbol === symbolOrCusip ? "monospace" : "inherit",
          }}
        >
          {displaySymbol}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 11,
            color: "var(--text-muted)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          持有 {heldCount} / {points.length} 個季度
          {someLoading && !allLoading && <span> · 更新中…</span>}
        </span>
      </div>

      {/* Sparkline strip — shares + value mini-charts */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 1,
          background: "var(--border-subtle)",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div style={{ padding: "12px 16px", background: "var(--bg-primary)" }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            Shares
          </div>
          <Sparkline points={points} metric="shares" />
        </div>
        <div style={{ padding: "12px 16px", background: "var(--bg-primary)" }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            Value (USD)
          </div>
          <Sparkline points={points} metric="valueUsd" />
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            fontSize: 12,
            borderCollapse: "collapse",
            color: "var(--foreground)",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-color)" }}>
              {["Period", "Shares", "Value", "Δ Shares", "Δ Value", "Status"].map(
                (label, idx) => (
                  <th
                    key={label}
                    style={{
                      padding: "10px 14px",
                      textAlign: idx === 0 || idx === 5 ? "left" : "right",
                      color: "var(--text-muted)",
                      fontWeight: 700,
                      letterSpacing: "0.06em",
                      fontSize: 10,
                      textTransform: "uppercase",
                      whiteSpace: "nowrap",
                      background: "var(--bg-secondary)",
                    }}
                  >
                    {label}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {/* Display newest → oldest for readability (matches snapshot view). */}
            {[...points].reverse().map((p, i) => {
              const isFirst = i === points.length - 1; // oldest row
              const deltaSharesColor =
                p.deltaShares == null
                  ? "var(--text-muted)"
                  : p.deltaShares > 0
                    ? "var(--stock-up)"
                    : p.deltaShares < 0
                      ? "var(--stock-down)"
                      : "var(--text-muted)";
              const deltaValueColor =
                p.deltaValue == null
                  ? "var(--text-muted)"
                  : p.deltaValue > 0
                    ? "var(--stock-up)"
                    : p.deltaValue < 0
                      ? "var(--stock-down)"
                      : "var(--text-muted)";
              return (
                <tr
                  key={p.period}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  <td
                    style={{
                      padding: "10px 14px",
                      fontFamily: "monospace",
                      fontVariantNumeric: "tabular-nums",
                      fontWeight: 600,
                    }}
                  >
                    {p.period}
                  </td>
                  <td
                    style={{
                      padding: "10px 14px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {p.holding ? fmtInt(p.shares) : "—"}
                  </td>
                  <td
                    style={{
                      padding: "10px 14px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      fontWeight: 600,
                    }}
                  >
                    {p.holding ? fmtCompact(p.valueUsd) : "—"}
                  </td>
                  <td
                    style={{
                      padding: "10px 14px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: deltaSharesColor,
                    }}
                  >
                    {p.deltaShares == null
                      ? "—"
                      : `${p.deltaShares > 0 ? "+" : ""}${fmtInt(
                          p.deltaShares,
                        )}${p.deltaPct != null ? ` (${fmtPct(p.deltaPct)})` : ""}`}
                  </td>
                  <td
                    style={{
                      padding: "10px 14px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: deltaValueColor,
                      fontWeight: 600,
                    }}
                  >
                    {p.deltaValue == null
                      ? "—"
                      : `${p.deltaValue > 0 ? "+" : ""}${fmtCompact(
                          p.deltaValue,
                        )}`}
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "left" }}>
                    <StatusCell point={p} isFirst={isFirst} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}
