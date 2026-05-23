"use client";

/**
 * Holdings Timeline — per-stock multi-quarter view for a single filer.
 *
 * Round 12 update: now backed by a single `/filers/{id}/holdings/{identifier}/history`
 * endpoint instead of N parallel `getHoldings` fan-outs. The backend handles
 * change_type classification + delta math, so this component is purely
 * presentational — it consumes the response, renders the sparkline + table.
 *
 * The previous fan-out pattern lives on as a fallback elsewhere if needed,
 * but the per-stock timeline is the canonical caller for the new endpoint.
 *
 * Color polarity follows the TAIWAN convention via `--stock-up` (red for
 * increases) and `--stock-down` (green for decreases), matching the rest
 * of the institutional UI.
 */

import { useMemo } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { useHoldingHistory } from "@/hooks/use-institutional";
import type { F13HoldingHistoryEntry } from "@/lib/api-client";
import { fmtCompact, fmtInt, fmtPct, toDecimal } from "./types";

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
  /** Raw entry from the backend — carries change_type + deltas. */
  entry: F13HoldingHistoryEntry;
  /** Δ shares vs previous period (already computed server-side). */
  deltaShares: number | null;
  /** Δ value vs previous period (derived locally — server only sends Δ shares). */
  deltaValue: number | null;
  /** Δ percent (shares basis) vs previous period (server-computed). */
  deltaPct: number | null;
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

function StatusCell({ point }: { point: TimelinePoint }) {
  switch (point.entry.change_type) {
    case "NOT_HELD":
      return (
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>未持有</span>
      );
    case "NEW":
      return (
        <span style={{ fontSize: 11, color: "var(--stock-up)", fontWeight: 600 }}>
          新建倉
        </span>
      );
    case "INCREASED":
      return (
        <span style={{ fontSize: 11, color: "var(--stock-up)", fontWeight: 600 }}>
          加碼
        </span>
      );
    case "DECREASED":
      return (
        <span
          style={{ fontSize: 11, color: "var(--stock-down)", fontWeight: 600 }}
        >
          減碼
        </span>
      );
    case "EXITED":
      return (
        <span
          style={{ fontSize: 11, color: "var(--stock-down)", fontWeight: 600 }}
        >
          已清倉
        </span>
      );
    case "UNCHANGED":
      return (
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>持平</span>
      );
    default:
      return (
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>—</span>
      );
  }
}

/* ------------------------------- Main -------------------------------- */

export function HoldingsTimeline({
  filerId,
  symbolOrCusip,
  maxQuarters = 8,
}: HoldingsTimelineProps) {
  const { data, isLoading } = useHoldingHistory(filerId, symbolOrCusip, {
    limit: maxQuarters,
  });

  /* Compose timeline rows. Backend returns ASC by report_period_end already,
   * with delta_* / change_type pre-computed. We just translate Decimal-as-string
   * to numbers and derive delta_value locally (server only sends delta_shares).
   */
  const points = useMemo<TimelinePoint[]>(() => {
    const entries = data?.entries ?? [];
    let prevValue: number | null = null;
    const rows: TimelinePoint[] = [];
    for (const entry of entries) {
      const shares = toDecimal(entry.shares);
      const valueUsd = toDecimal(entry.value_usd);
      const deltaShares = toDecimal(entry.delta_shares);
      const deltaPct = toDecimal(entry.delta_pct);
      const deltaValue =
        prevValue != null && valueUsd != null ? valueUsd - prevValue : null;
      rows.push({
        period: entry.report_period_end,
        shares,
        valueUsd,
        entry,
        deltaShares,
        deltaValue,
        deltaPct,
      });
      prevValue = valueUsd;
    }
    return rows;
  }, [data]);

  const displaySymbol = useMemo(() => {
    if (data?.symbol) return data.symbol;
    if (data?.cusip) return data.cusip;
    return symbolOrCusip;
  }, [data, symbolOrCusip]);

  /* --------------------------- Render --------------------------- */

  if (isLoading) {
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

  if (points.length === 0) {
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

  const heldCount = points.filter(
    (p) => p.entry.change_type !== "NOT_HELD",
  ).length;

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
            {[...points].reverse().map((p) => {
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
              const isNotHeld = p.entry.change_type === "NOT_HELD";
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
                    {isNotHeld ? "—" : fmtInt(p.shares)}
                  </td>
                  <td
                    style={{
                      padding: "10px 14px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      fontWeight: 600,
                    }}
                  >
                    {isNotHeld ? "—" : fmtCompact(p.valueUsd)}
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
                    <StatusCell point={p} />
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
