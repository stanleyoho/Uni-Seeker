"use client";

/**
 * Institutional Holdings Table — per-period rows of a filer's 13F.
 *
 * Distinct from `components/holdings/holdings-table.tsx` (user-owned
 * positions). Columns:
 *
 *   - Symbol/CUSIP — symbol if the CUSIP is mapped, else raw CUSIP.
 *   - Issuer       — `name_of_issuer` from EDGAR (free-text, not normalised).
 *   - Shares       — total share count.
 *   - Value USD    — market value + percent of total portfolio (computed).
 *   - Put/Call     — option flag badge (only renders when non-null).
 *   - Discretion   — SOLE / SHARED / NONE.
 *
 * Sort defaults to `value_usd desc` so the largest positions surface
 * first. Percent-of-portfolio is computed on the client by dividing each
 * row's `value_usd` by the sum across the rendered set — this matches
 * what users expect when filtering a sub-set, but DOES diverge from the
 * filing's authoritative `total_value_usd` (which includes options
 * notional). The diff is intentionally small in Phase 2 and called out
 * in the column header (just "%" — not "% of 13F AUM").
 */

import { useMemo, useState } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import {
  fmtCompact,
  fmtInt,
  holdingDisplaySymbol,
  toDecimal,
  type F13Holding,
} from "./types";

export interface InstitutionalHoldingsTableProps {
  holdings: F13Holding[];
  loading?: boolean;
  /**
   * Optional row click handler. When provided, rows become focusable and
   * clickable — used by Round 11 to drive the per-stock Timeline view from
   * the main page. Omit for read-only callers (no behaviour change).
   */
  onRowClick?: (holding: F13Holding) => void;
}

type SortKey =
  | "symbol"
  | "name_of_issuer"
  | "shares"
  | "value_usd"
  | "put_call"
  | "investment_discretion";

type SortDir = "asc" | "desc";

interface ColumnDef {
  key: SortKey;
  label: string;
  align: "left" | "right";
  minWidth: number;
}

const COLUMNS: ColumnDef[] = [
  { key: "symbol", label: "Symbol / CUSIP", align: "left", minWidth: 140 },
  { key: "name_of_issuer", label: "Issuer", align: "left", minWidth: 200 },
  { key: "shares", label: "Shares", align: "right", minWidth: 110 },
  { key: "value_usd", label: "Value (USD)", align: "right", minWidth: 130 },
  { key: "put_call", label: "Type", align: "right", minWidth: 70 },
  {
    key: "investment_discretion",
    label: "Discretion",
    align: "right",
    minWidth: 90,
  },
];

interface DerivedRow {
  raw: F13Holding;
  shares: number | null;
  value_usd: number;
  /** Percent of the rendered set's total value — computed below. */
  pct_of_total: number;
}

function compareRows(a: DerivedRow, b: DerivedRow, key: SortKey): number {
  switch (key) {
    case "symbol":
      return holdingDisplaySymbol(a.raw).localeCompare(
        holdingDisplaySymbol(b.raw),
      );
    case "name_of_issuer":
      return a.raw.name_of_issuer.localeCompare(b.raw.name_of_issuer);
    case "shares": {
      const av = a.shares ?? Number.NEGATIVE_INFINITY;
      const bv = b.shares ?? Number.NEGATIVE_INFINITY;
      return av - bv;
    }
    case "value_usd":
      return a.value_usd - b.value_usd;
    case "put_call": {
      const av = a.raw.put_call ?? "";
      const bv = b.raw.put_call ?? "";
      return av.localeCompare(bv);
    }
    case "investment_discretion": {
      const av = a.raw.investment_discretion ?? "";
      const bv = b.raw.investment_discretion ?? "";
      return av.localeCompare(bv);
    }
  }
}

interface HeaderCellProps {
  col: ColumnDef;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}

function HeaderCell({ col, active, dir, onClick }: HeaderCellProps) {
  const arrow = active ? (dir === "asc" ? "▲" : "▼") : "";
  return (
    <th
      onClick={onClick}
      style={{
        padding: "10px 14px",
        textAlign: col.align,
        color: active ? "var(--accent-cyan)" : "var(--text-muted)",
        fontWeight: 700,
        letterSpacing: "0.06em",
        fontSize: 10,
        textTransform: "uppercase",
        cursor: "pointer",
        userSelect: "none",
        whiteSpace: "nowrap",
        minWidth: col.minWidth,
        background: "var(--bg-secondary)",
        position: "sticky",
        top: 0,
        zIndex: 1,
      }}
    >
      <span>{col.label}</span>
      {arrow && <span style={{ marginLeft: 4, fontSize: 9 }}>{arrow}</span>}
    </th>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {COLUMNS.map((c) => (
        <td key={c.key} style={{ padding: "10px 14px", textAlign: c.align }}>
          <div
            style={{
              height: 12,
              background: "var(--card-hover)",
              width: c.align === "right" ? 70 : 120,
              marginLeft: c.align === "right" ? "auto" : 0,
            }}
          />
        </td>
      ))}
    </tr>
  );
}

function PutCallBadge({ value }: { value: "PUT" | "CALL" | null }) {
  if (!value) {
    return <span style={{ color: "var(--text-muted)", fontSize: 11 }}>—</span>;
  }
  // PUT  = downside  = TW convention green
  // CALL = upside    = TW convention red
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
      }}
    >
      {value}
    </span>
  );
}

export function InstitutionalHoldingsTable({
  holdings,
  loading = false,
  onRowClick,
}: InstitutionalHoldingsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("value_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  /* Pre-derive numbers + percent-of-portfolio in one pass. */
  const { rows, totalValue } = useMemo(() => {
    const derivedNoPct: Omit<DerivedRow, "pct_of_total">[] = holdings.map(
      (h) => ({
        raw: h,
        shares: toDecimal(h.shares),
        value_usd: toDecimal(h.value_usd) ?? 0,
      }),
    );
    const total = derivedNoPct.reduce((sum, r) => sum + r.value_usd, 0);
    const withPct: DerivedRow[] = derivedNoPct.map((r) => ({
      ...r,
      pct_of_total: total > 0 ? (r.value_usd / total) * 100 : 0,
    }));
    withPct.sort((a, b) => {
      const cmp = compareRows(a, b, sortKey);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return { rows: withPct, totalValue: total };
  }, [holdings, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(
        key === "symbol" || key === "name_of_issuer" ? "asc" : "desc",
      );
    }
  };

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
              {COLUMNS.map((col) => (
                <HeaderCell
                  key={col.key}
                  col={col}
                  active={sortKey === col.key}
                  dir={sortDir}
                  onClick={() => handleSort(col.key)}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : rows.map((r) => (
                  <tr
                    key={`${r.raw.id}`}
                    onClick={onRowClick ? () => onRowClick(r.raw) : undefined}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      transition: "background 0.12s",
                      cursor: onRowClick ? "pointer" : "default",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "var(--card-hover)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    {/* Symbol / CUSIP */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "left",
                        fontWeight: 700,
                        fontSize: 13,
                        color: "var(--foreground)",
                        fontFamily: r.raw.stock_symbol
                          ? "inherit"
                          : "monospace",
                      }}
                    >
                      {holdingDisplaySymbol(r.raw)}
                    </td>

                    {/* Issuer */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "left",
                        color: "var(--text-secondary)",
                        fontSize: 12,
                        maxWidth: 280,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={r.raw.name_of_issuer}
                    >
                      {r.raw.name_of_issuer}
                    </td>

                    {/* Shares */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {fmtInt(r.shares)}
                    </td>

                    {/* Value USD + % */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                        fontWeight: 600,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "flex-end",
                          gap: 2,
                        }}
                      >
                        <span>{fmtCompact(r.value_usd)}</span>
                        <span
                          style={{
                            fontSize: 10,
                            color: "var(--text-muted)",
                            fontWeight: 400,
                          }}
                        >
                          {totalValue > 0
                            ? `${r.pct_of_total.toFixed(2)}%`
                            : "—"}
                        </span>
                      </div>
                    </td>

                    {/* Put/Call */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "right",
                      }}
                    >
                      <PutCallBadge value={r.raw.put_call} />
                    </td>

                    {/* Discretion */}
                    <td
                      style={{
                        padding: "10px 14px",
                        textAlign: "right",
                        fontSize: 11,
                        color: "var(--text-secondary)",
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                      }}
                    >
                      {r.raw.investment_discretion ?? "—"}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}
