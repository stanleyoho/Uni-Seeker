"use client";

/**
 * Top Movers — biggest buys/sells over a QoQ window.
 *
 * Thin presentational layer over `useDiff`. We split the change set into
 * "buys" (NEW + INCREASED) vs "sells" (DECREASED + EXITED), rank each by
 * `abs(delta_value_usd)` desc, and truncate to `limit` (default 10) on
 * each side.
 *
 * Layout: two-column grid on desktop, stacked on narrow screens (handled
 * via CSS `grid-template-columns` w/ `minmax`). Cells show:
 *   - Symbol/CUSIP (mono if unmapped)
 *   - Change-type badge (新增/加碼 vs 減碼/清倉)
 *   - Δ shares / Δ value
 *
 * Color convention: TW (red = up = NEW/INCREASED, green = down =
 * DECREASED/EXITED) via `changeTypeColor`.
 */

import { useMemo } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { useDiff } from "@/hooks/use-institutional";
import { ApiError } from "@/lib/api-client";
import {
  changeTypeColor,
  changeTypeLabel,
  fmtCompact,
  fmtInt,
  toDecimal,
  type F13ChangeType,
  type F13HoldingChange,
} from "./types";

export interface TopMoversProps {
  filerId: number;
  fromDate: string;
  toDate: string;
  /** Number of items per column. Default 10. */
  limit?: number;
}

const BUY_TYPES = new Set<F13ChangeType>(["NEW", "INCREASED"]);
const SELL_TYPES = new Set<F13ChangeType>(["DECREASED", "EXITED"]);

interface MoverRow {
  raw: F13HoldingChange;
  deltaShares: number;
  deltaValue: number;
}

function rankMovers(changes: F13HoldingChange[]): {
  buys: MoverRow[];
  sells: MoverRow[];
} {
  const buys: MoverRow[] = [];
  const sells: MoverRow[] = [];
  for (const c of changes) {
    const row: MoverRow = {
      raw: c,
      deltaShares: toDecimal(c.delta_shares) ?? 0,
      deltaValue: toDecimal(c.delta_value_usd) ?? 0,
    };
    if (BUY_TYPES.has(c.change_type as F13ChangeType)) {
      buys.push(row);
    } else if (SELL_TYPES.has(c.change_type as F13ChangeType)) {
      sells.push(row);
    }
  }
  buys.sort((a, b) => Math.abs(b.deltaValue) - Math.abs(a.deltaValue));
  sells.sort((a, b) => Math.abs(b.deltaValue) - Math.abs(a.deltaValue));
  return { buys, sells };
}

function mapDiffError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "載入失敗";
  }
  if (err.status === 404) {
    return "缺少對應期間的 filing — 請先 refresh 拉資料";
  }
  return err.message || "載入失敗";
}

function MoverItem({ row }: { row: MoverRow }) {
  const color = changeTypeColor(row.raw.change_type);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 14px",
        borderBottom: "1px solid var(--border-subtle)",
        gap: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 2,
          minWidth: 0,
          flex: 1,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span
            style={{
              fontFamily: "monospace",
              fontSize: 13,
              fontWeight: 700,
              color: "var(--foreground)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {row.raw.cusip}
          </span>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: "2px 6px",
              background: `color-mix(in srgb, ${color} 18%, transparent)`,
              color,
              border: `1px solid ${color}`,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {changeTypeLabel(row.raw.change_type)}
          </span>
        </div>
        <span
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={row.raw.name_of_issuer}
        >
          {row.raw.name_of_issuer}
        </span>
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
          gap: 2,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color,
          }}
        >
          {row.deltaValue > 0 ? "+" : ""}
          {fmtCompact(row.deltaValue)}
        </span>
        <span
          style={{
            fontSize: 10,
            color: "var(--text-muted)",
          }}
        >
          Δ {fmtInt(row.deltaShares)} 股
        </span>
      </div>
    </div>
  );
}

function MoverColumn({
  title,
  rows,
  emptyHint,
  accentColor,
}: {
  title: string;
  rows: MoverRow[];
  emptyHint: string;
  accentColor: string;
}) {
  return (
    <GlassPanel noPadding>
      <div
        style={{
          padding: "10px 14px",
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.1em",
          color: accentColor,
          textTransform: "uppercase",
          background: "var(--bg-secondary)",
          borderBottom: `1px solid ${accentColor}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <span>{title}</span>
        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
          {rows.length} 筆
        </span>
      </div>
      {rows.length === 0 ? (
        <p
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            textAlign: "center",
            padding: "32px 0",
          }}
        >
          {emptyHint}
        </p>
      ) : (
        rows.map((r) => <MoverItem key={r.raw.cusip} row={r} />)
      )}
    </GlassPanel>
  );
}

export function TopMovers({
  filerId,
  fromDate,
  toDate,
  limit = 10,
}: TopMoversProps) {
  const queryReady = fromDate.length > 0 && toDate.length > 0;
  const { data, isLoading, error } = useDiff(
    queryReady ? filerId : null,
    fromDate,
    toDate,
  );

  const { buys, sells } = useMemo(() => {
    if (!data) return { buys: [], sells: [] };
    return rankMovers(data.changes);
  }, [data]);

  if (!queryReady) {
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
          選擇兩個期間以查看 Top Movers
        </p>
      </GlassPanel>
    );
  }

  if (error) {
    return (
      <GlassPanel>
        <p
          style={{
            fontSize: 12,
            color: "var(--accent-primary)",
            fontWeight: 600,
            padding: "20px 0",
            textAlign: "center",
          }}
        >
          {mapDiffError(error)}
        </p>
      </GlassPanel>
    );
  }

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

  return (
    <div
      style={{
        display: "grid",
        // 280px floor lets a single column survive on phone viewports
        // (375px - 24px page padding = 351px) while still side-by-siding
        // on tablet+. `auto-fit` collapses to 1 col automatically.
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: 16,
      }}
    >
      <MoverColumn
        title="TOP BUYS · 新增 / 加碼"
        rows={buys.slice(0, limit)}
        emptyHint="本期無新增 / 加碼"
        accentColor="var(--stock-up)"
      />
      <MoverColumn
        title="TOP SELLS · 減碼 / 清倉"
        rows={sells.slice(0, limit)}
        emptyHint="本期無減碼 / 清倉"
        accentColor="var(--stock-down)"
      />
    </div>
  );
}
