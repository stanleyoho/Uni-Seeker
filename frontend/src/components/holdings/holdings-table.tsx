"use client";

/**
 * Holdings Table — sortable, multi-select positions grid.
 *
 * Layout & visual rules:
 *   - GlassPanel wrapper (noPadding so the table can flush to edge).
 *   - Sticky header row, border-bottom = var(--border-color).
 *   - Numeric cells right-aligned + `tabular-nums`.
 *   - Hover row → background var(--card-hover).
 *   - Selected checkbox accent → var(--accent-cyan).
 *   - P&L / change cells colored via pnlColor().
 *
 * Sort behaviour:
 *   - Click any header → cycles asc/desc on that column.
 *   - Selected column shows arrow indicator.
 *   - Sort comparators read Decimal-as-string via toNumber().
 */
import React, { useMemo, useState, type ReactNode } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { MarketBadge } from "@/components/ui/badge";
import {
  type HoldingPosition,
  toNumber,
  fmt,
  fmtSigned,
  pnlColor,
} from "./types";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export interface HoldingsTableProps {
  positions: HoldingPosition[];
  loading?: boolean;
  onRowClick?: (position: HoldingPosition) => void;
  selectedSymbols?: string[];
  onSelectionChange?: (symbols: string[]) => void;
  emptyState?: ReactNode;
}

type SortKey =
  | "symbol"
  | "qty"
  | "avg_cost"
  | "last_price"
  | "market_value"
  | "unrealized_pnl"
  | "unrealized_pnl_pct"
  | "daily_change"
  | "daily_change_pct";

type SortDir = "asc" | "desc";

interface ColumnDef {
  key: SortKey;
  label: string;
  align: "left" | "right";
  /** Pixel min-width to prevent column collapse on small screens. */
  minWidth?: number;
  /**
   * Tailwind class that controls breakpoint visibility for this column.
   * Used to hide low-signal columns on phone-sized viewports — the table
   * still scrolls horizontally for any remaining overflow.
   *
   *   - undefined          → always visible
   *   - "hidden sm:table-cell" → tablet+ only (≥640px)
   *   - "hidden lg:table-cell" → desktop only (≥1024px)
   */
  responsiveClass?: string;
}

const COLUMNS: ColumnDef[] = [
  { key: "symbol", label: "Symbol", align: "left", minWidth: 110 },
  { key: "qty", label: "Qty", align: "right", minWidth: 70 },
  { key: "avg_cost", label: "Avg Cost", align: "right", minWidth: 90, responsiveClass: "hidden sm:table-cell" },
  { key: "last_price", label: "Last", align: "right", minWidth: 80 },
  { key: "market_value", label: "Market Value", align: "right", minWidth: 110 },
  { key: "unrealized_pnl", label: "Unrealized P&L", align: "right", minWidth: 120, responsiveClass: "hidden md:table-cell" },
  { key: "unrealized_pnl_pct", label: "Unrealized %", align: "right", minWidth: 100, responsiveClass: "hidden lg:table-cell" },
  { key: "daily_change", label: "Daily Δ", align: "right", minWidth: 100, responsiveClass: "hidden lg:table-cell" },
  { key: "daily_change_pct", label: "Daily %", align: "right", minWidth: 90, responsiveClass: "hidden lg:table-cell" },
];

/* ------------------------------------------------------------------ */
/*  Derived row — numbers pre-converted so render is cheap & sort     */
/*  comparators share the same source of truth.                       */
/* ------------------------------------------------------------------ */

interface DerivedRow {
  raw: HoldingPosition;
  qty: number;
  avg_cost: number | null;
  last_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  daily_change: number | null;
  daily_change_pct: number | null;
}

function derive(p: HoldingPosition): DerivedRow {
  const qty = toNumber(p.qty) ?? 0;
  const last = toNumber(p.last_price);
  const marketValue = last != null ? qty * last : null;
  return {
    raw: p,
    qty,
    avg_cost: toNumber(p.avg_cost),
    last_price: last,
    market_value: marketValue,
    unrealized_pnl: toNumber(p.unrealized_pnl),
    unrealized_pnl_pct: toNumber(p.unrealized_pnl_pct),
    daily_change: toNumber(p.daily_change),
    daily_change_pct: toNumber(p.daily_change_pct),
  };
}

/* ------------------------------------------------------------------ */
/*  Sort                                                               */
/* ------------------------------------------------------------------ */

function compareRows(a: DerivedRow, b: DerivedRow, key: SortKey): number {
  if (key === "symbol") return a.raw.symbol.localeCompare(b.raw.symbol);

  const av = a[key];
  const bv = b[key];
  const an = av == null ? Number.NEGATIVE_INFINITY : av;
  const bn = bv == null ? Number.NEGATIVE_INFINITY : bv;
  return an - bn;
}

/* ------------------------------------------------------------------ */
/*  Header cell with sort indicator                                    */
/* ------------------------------------------------------------------ */

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
      className={col.responsiveClass}
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
      {arrow && (
        <span style={{ marginLeft: 4, fontSize: 9 }}>{arrow}</span>
      )}
    </th>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading skeleton row                                               */
/* ------------------------------------------------------------------ */

function SkeletonRow() {
  return (
    <tr>
      <td style={{ padding: "10px 14px" }}>
        <div style={{ width: 14, height: 14, background: "var(--card-hover)" }} />
      </td>
      {COLUMNS.map((c) => (
        <td
          key={c.key}
          className={c.responsiveClass}
          style={{ padding: "10px 14px", textAlign: c.align }}
        >
          <div
            style={{
              height: 12,
              background: "var(--card-hover)",
              width: c.align === "right" ? 60 : 100,
              marginLeft: c.align === "right" ? "auto" : 0,
            }}
          />
        </td>
      ))}
    </tr>
  );
}

// Lookup map so render-time td can pull its responsive class by key
// without scanning COLUMNS each render.
const COL_CLASS_BY_KEY: Partial<Record<SortKey, string>> = Object.fromEntries(
  COLUMNS.filter((c) => c.responsiveClass).map((c) => [c.key, c.responsiveClass!]),
);

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function HoldingsTable({
  positions,
  loading = false,
  onRowClick,
  selectedSymbols,
  onSelectionChange,
  emptyState,
}: HoldingsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("market_value");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const selectedSet = useMemo(
    () => new Set(selectedSymbols ?? []),
    [selectedSymbols],
  );
  const selectionEnabled = !!onSelectionChange;

  const rows = useMemo(() => {
    const derived = positions.map(derive);
    derived.sort((a, b) => {
      const cmp = compareRows(a, b, sortKey);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return derived;
  }, [positions, sortKey, sortDir]);

  const allSelected =
    selectionEnabled && rows.length > 0 && selectedSet.size === rows.length;
  const someSelected =
    selectionEnabled && selectedSet.size > 0 && selectedSet.size < rows.length;

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "symbol" ? "asc" : "desc");
    }
  };

  const toggleOne = (symbol: string) => {
    if (!onSelectionChange) return;
    const next = new Set(selectedSet);
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    onSelectionChange(Array.from(next));
  };

  const toggleAll = () => {
    if (!onSelectionChange) return;
    if (allSelected) onSelectionChange([]);
    else onSelectionChange(rows.map((r) => r.raw.symbol));
  };

  /* -------- Empty / loading / data render branches -------- */

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
          {emptyState ?? "無持倉。點 + Add Trade 開始記錄。"}
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
              {selectionEnabled && (
                <th
                  style={{
                    padding: "10px 14px",
                    width: 36,
                    background: "var(--bg-secondary)",
                    position: "sticky",
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected;
                    }}
                    onChange={toggleAll}
                    style={{
                      accentColor: "var(--accent-cyan)",
                      cursor: "pointer",
                      width: 14,
                      height: 14,
                    }}
                  />
                </th>
              )}
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
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              : rows.map((r) => {
                  const sel = selectedSet.has(r.raw.symbol);
                  return (
                    <tr
                      key={`${r.raw.account_id}-${r.raw.symbol}`}
                      onClick={() => onRowClick?.(r.raw)}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        background: sel
                          ? "var(--card-active)"
                          : "transparent",
                        cursor: onRowClick ? "pointer" : "default",
                        transition: "background 0.12s",
                      }}
                      onMouseEnter={(e) => {
                        if (!sel)
                          e.currentTarget.style.background =
                            "var(--card-hover)";
                      }}
                      onMouseLeave={(e) => {
                        if (!sel)
                          e.currentTarget.style.background = "transparent";
                      }}
                    >
                      {selectionEnabled && (
                        <td
                          style={{ padding: "10px 14px" }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={sel}
                            onChange={() => toggleOne(r.raw.symbol)}
                            style={{
                              accentColor: "var(--accent-cyan)",
                              cursor: "pointer",
                              width: 14,
                              height: 14,
                            }}
                          />
                        </td>
                      )}

                      {/* Symbol */}
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "left",
                          fontWeight: 700,
                          fontSize: 13,
                          color: "var(--foreground)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <span>{r.raw.symbol}</span>
                          <MarketBadge market={r.raw.market} />
                        </div>
                      </td>

                      {/* Qty */}
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {fmt(r.qty, r.qty % 1 === 0 ? 0 : 4)}
                      </td>

                      {/* Avg Cost */}
                      <td
                        className={COL_CLASS_BY_KEY.avg_cost}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {fmt(r.avg_cost, 2)}
                      </td>

                      {/* Last Price */}
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {fmt(r.last_price, 2)}
                      </td>

                      {/* Market Value */}
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: 600,
                        }}
                      >
                        {fmt(r.market_value, 0)}
                      </td>

                      {/* Unrealized P&L */}
                      <td
                        className={COL_CLASS_BY_KEY.unrealized_pnl}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: pnlColor(r.unrealized_pnl),
                          fontWeight: 600,
                        }}
                      >
                        {fmtSigned(r.unrealized_pnl, 0)}
                      </td>

                      {/* Unrealized % */}
                      <td
                        className={COL_CLASS_BY_KEY.unrealized_pnl_pct}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: pnlColor(r.unrealized_pnl_pct),
                        }}
                      >
                        {r.unrealized_pnl_pct == null
                          ? "—"
                          : `${r.unrealized_pnl_pct >= 0 ? "+" : ""}${r.unrealized_pnl_pct.toFixed(2)}%`}
                      </td>

                      {/* Daily Change */}
                      <td
                        className={COL_CLASS_BY_KEY.daily_change}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: pnlColor(r.daily_change),
                        }}
                      >
                        {fmtSigned(r.daily_change, 0)}
                      </td>

                      {/* Daily % */}
                      <td
                        className={COL_CLASS_BY_KEY.daily_change_pct}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: pnlColor(r.daily_change_pct),
                        }}
                      >
                        {r.daily_change_pct == null
                          ? "—"
                          : `${r.daily_change_pct >= 0 ? "+" : ""}${r.daily_change_pct.toFixed(2)}%`}
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
