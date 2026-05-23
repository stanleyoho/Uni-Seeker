"use client";

/**
 * Filer List — STRATOS sortable table of subscribed filers.
 *
 * Each row represents one entry in the user's `f13_user_subscriptions`.
 * Clicking a row notifies the parent (which then drives holdings / diff
 * panes for the selected filer). Sort cycles asc → desc on the active
 * column; clicking a different column resets the direction to `desc` for
 * value-shaped columns and `asc` for name/cik.
 *
 * Loading state renders 4 skeleton rows so layout doesn't jump.
 * Empty state is a single CTA-style block ("尚未訂閱任何機構/基金").
 */

import { useMemo, useState } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import {
  fmtCompact,
  fmtInt,
  toDecimal,
  type F13Filer,
} from "./types";

export interface FilerListProps {
  filers: F13Filer[];
  selectedFilerId: number | null;
  onSelect: (filerId: number) => void;
  loading?: boolean;
  /** Slot for the "+ 訂閱機構/基金" CTA shown in the empty state. */
  emptyCta?: React.ReactNode;
}

type SortKey =
  | "name"
  | "cik"
  | "latest_filing_date"
  | "latest_total_value_usd"
  | "latest_position_count";

type SortDir = "asc" | "desc";

interface ColumnDef {
  key: SortKey;
  label: string;
  align: "left" | "right";
  minWidth: number;
  /** Optional Tailwind visibility class for breakpoint-gated columns. */
  responsiveClass?: string;
}

const COLUMNS: ColumnDef[] = [
  { key: "name", label: "Filer", align: "left", minWidth: 160 },
  { key: "cik", label: "CIK", align: "left", minWidth: 100, responsiveClass: "hidden md:table-cell" },
  { key: "latest_filing_date", label: "Latest Filing", align: "right", minWidth: 120, responsiveClass: "hidden sm:table-cell" },
  { key: "latest_total_value_usd", label: "13F AUM", align: "right", minWidth: 100 },
  { key: "latest_position_count", label: "Positions", align: "right", minWidth: 80, responsiveClass: "hidden lg:table-cell" },
];

const FL_COL_CLASS_BY_KEY: Partial<Record<SortKey, string>> = Object.fromEntries(
  COLUMNS.filter((c) => c.responsiveClass).map((c) => [c.key, c.responsiveClass!]),
);

interface DerivedRow {
  raw: F13Filer;
  total_value: number | null;
  position_count: number | null;
  /** Sortable string form of the filing date (or empty string for nulls). */
  filing_date_sortable: string;
}

function derive(f: F13Filer): DerivedRow {
  return {
    raw: f,
    total_value: toDecimal(f.latest_total_value_usd),
    position_count: f.latest_position_count,
    filing_date_sortable: f.latest_filing_date ?? "",
  };
}

function compareRows(a: DerivedRow, b: DerivedRow, key: SortKey): number {
  switch (key) {
    case "name":
      return a.raw.name.localeCompare(b.raw.name);
    case "cik":
      return a.raw.cik.localeCompare(b.raw.cik);
    case "latest_filing_date":
      // Empty strings sort to the bottom in ascending order; that matches
      // "no filing yet" being the least informative entry.
      return a.filing_date_sortable.localeCompare(b.filing_date_sortable);
    case "latest_total_value_usd": {
      const av = a.total_value ?? Number.NEGATIVE_INFINITY;
      const bv = b.total_value ?? Number.NEGATIVE_INFINITY;
      return av - bv;
    }
    case "latest_position_count": {
      const av = a.position_count ?? Number.NEGATIVE_INFINITY;
      const bv = b.position_count ?? Number.NEGATIVE_INFINITY;
      return av - bv;
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
      {arrow && <span style={{ marginLeft: 4, fontSize: 9 }}>{arrow}</span>}
    </th>
  );
}

function SkeletonRow() {
  return (
    <tr>
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
              width: c.align === "right" ? 60 : 120,
              marginLeft: c.align === "right" ? "auto" : 0,
            }}
          />
        </td>
      ))}
    </tr>
  );
}

export function FilerList({
  filers,
  selectedFilerId,
  onSelect,
  loading = false,
  emptyCta,
}: FilerListProps) {
  const [sortKey, setSortKey] = useState<SortKey>("latest_total_value_usd");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const rows = useMemo(() => {
    const derived = filers.map(derive);
    derived.sort((a, b) => {
      const cmp = compareRows(a, b, sortKey);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return derived;
  }, [filers, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" || key === "cik" ? "asc" : "desc");
    }
  };

  if (!loading && rows.length === 0) {
    return (
      <GlassPanel noPadding>
        <div
          style={{
            padding: "48px 24px",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
          }}
        >
          <p
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: "var(--foreground)",
              letterSpacing: "0.02em",
            }}
          >
            尚未訂閱任何機構 / 基金
          </p>
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
            從 SEC EDGAR 搜尋 13F 申報人 (例：Berkshire Hathaway / ARK)
          </p>
          {emptyCta}
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
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
              : rows.map((r) => {
                  const sel = selectedFilerId === r.raw.id;
                  return (
                    <tr
                      key={r.raw.id}
                      onClick={() => onSelect(r.raw.id)}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        background: sel
                          ? "var(--card-active)"
                          : "transparent",
                        cursor: "pointer",
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
                      {/* Name */}
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
                            flexDirection: "column",
                            gap: 2,
                          }}
                        >
                          <span>{r.raw.name}</span>
                          {r.raw.legal_name &&
                            r.raw.legal_name !== r.raw.name && (
                              <span
                                style={{
                                  fontSize: 10,
                                  color: "var(--text-muted)",
                                  fontWeight: 400,
                                }}
                              >
                                {r.raw.legal_name}
                              </span>
                            )}
                        </div>
                      </td>

                      {/* CIK */}
                      <td
                        className={FL_COL_CLASS_BY_KEY.cik}
                        style={{
                          padding: "10px 14px",
                          textAlign: "left",
                          fontFamily: "monospace",
                          fontSize: 11,
                          color: "var(--text-secondary)",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {r.raw.cik}
                      </td>

                      {/* Latest filing date */}
                      <td
                        className={FL_COL_CLASS_BY_KEY.latest_filing_date}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: r.raw.latest_filing_date
                            ? "var(--foreground)"
                            : "var(--text-muted)",
                        }}
                      >
                        {r.raw.latest_filing_date ?? "—"}
                      </td>

                      {/* 13F AUM */}
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          fontWeight: 600,
                        }}
                      >
                        {fmtCompact(r.total_value)}
                      </td>

                      {/* Position count */}
                      <td
                        className={FL_COL_CLASS_BY_KEY.latest_position_count}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {fmtInt(r.position_count)}
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
