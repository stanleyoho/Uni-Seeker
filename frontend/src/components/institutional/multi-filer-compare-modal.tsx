"use client";

/**
 * Multi-Filer Compare Modal — side-by-side latest-holdings matrix.
 *
 * Workflow:
 *   1. User picks up to MAX_FILERS (5) from their subscribed filer list.
 *   2. For each selected filer, we fan out two queries:
 *        a) `useFilings(filerId)` to discover latest + prev period.
 *        b) `getHoldings(filerId, "latest")` for the snapshot.
 *        c) `getHoldings(filerId, prev_period)` to compute QoQ direction
 *           per cell (so cell borders can flag "reduced" / "added"
 *           positions relative to the prior quarter).
 *   3. Union of CUSIPs across all selected filers becomes the row set.
 *   4. Sort rows by total_value desc (default) or by # of filers holding.
 *
 * Cell styling:
 *   - Held & latest only          → normal
 *   - Held & added vs prev        → green border (TW: up = red, but here
 *                                    we keep cyan/green for "diff added"
 *                                    to distinguish from raw value sign)
 *   - Held & reduced vs prev      → red border
 *   - Not held                    → "—" gray cell
 *
 * Implementation notes:
 *   - Hooks are dispatched via `useQueries`, so the hook count is stable
 *     across renders even when the selection set grows.
 *   - Compare grid is render-virtualised only loosely (max 5 filers × ~200
 *     rows = 1000 cells); plain table is fine, no need for react-window.
 */

import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import {
  getHoldings,
  listFilings,
  type F13Filing,
  type F13HoldingsAtPeriod,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import { useInstitutionalFilers } from "@/hooks/use-institutional";
import {
  fmtCompact,
  fmtInt,
  holdingDisplaySymbol,
  toDecimal,
  type F13Filer,
  type F13Holding,
} from "./types";

const MAX_FILERS = 5;

export interface MultiFilerCompareModalProps {
  /** Optional pre-selection (e.g. caller pre-selects current filer). */
  preselectedFilerIds?: number[];
  onClose: () => void;
}

type SortKey = "value" | "filer_count";

/* Per-filer compose snapshot. */
interface FilerSnapshot {
  filer: F13Filer;
  latest: F13HoldingsAtPeriod | null;
  prev: F13HoldingsAtPeriod | null;
  loading: boolean;
}

/* CUSIP → cell info. */
interface CellInfo {
  held: boolean;
  shares: number | null;
  value: number | null;
  /** "up" → added shares vs prev. "down" → reduced. null → no prev to compare. */
  direction: "up" | "down" | "flat" | null;
}

interface CompareRow {
  cusip: string;
  /** Best-effort display symbol (first filer's mapping wins). */
  displaySymbol: string;
  issuer: string;
  /** Sum of value_usd across filers that hold it (latest period). */
  totalValue: number;
  filerCount: number;
  /** filer_id → cell info. */
  cells: Map<number, CellInfo>;
}

function indexHoldings(snapshot: F13HoldingsAtPeriod | null): Map<string, F13Holding> {
  const map = new Map<string, F13Holding>();
  if (!snapshot) return map;
  for (const h of snapshot.holdings) {
    map.set(h.cusip, h);
  }
  return map;
}

function buildRows(snapshots: FilerSnapshot[]): CompareRow[] {
  const byCusip = new Map<string, CompareRow>();

  for (const snap of snapshots) {
    if (!snap.latest) continue;
    const prevIdx = indexHoldings(snap.prev);

    for (const h of snap.latest.holdings) {
      let row = byCusip.get(h.cusip);
      if (!row) {
        row = {
          cusip: h.cusip,
          displaySymbol: holdingDisplaySymbol(h),
          issuer: h.name_of_issuer,
          totalValue: 0,
          filerCount: 0,
          cells: new Map(),
        };
        byCusip.set(h.cusip, row);
      } else if (row.displaySymbol === row.cusip && h.stock_symbol) {
        // Prefer a mapped symbol if any filer has it.
        row.displaySymbol = h.stock_symbol;
      }

      const shares = toDecimal(h.shares);
      const value = toDecimal(h.value_usd) ?? 0;
      row.totalValue += value;
      row.filerCount += 1;

      let direction: CellInfo["direction"] = null;
      if (snap.prev) {
        const prevH = prevIdx.get(h.cusip);
        if (!prevH) {
          direction = "up"; // new vs prev → added
        } else {
          const prevShares = toDecimal(prevH.shares) ?? 0;
          const currShares = shares ?? 0;
          if (currShares > prevShares) direction = "up";
          else if (currShares < prevShares) direction = "down";
          else direction = "flat";
        }
      }

      row.cells.set(snap.filer.id, {
        held: true,
        shares,
        value,
        direction,
      });
    }
  }

  return Array.from(byCusip.values());
}

/* ----------------------------- Filer picker ---------------------------- */

function FilerPicker({
  filers,
  selectedIds,
  onToggle,
}: {
  filers: F13Filer[];
  selectedIds: Set<number>;
  onToggle: (id: number) => void;
}) {
  if (filers.length === 0) {
    return (
      <p
        style={{
          fontSize: 12,
          color: "var(--text-muted)",
          padding: "8px 0",
        }}
      >
        尚未訂閱任何 filer
      </p>
    );
  }
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
        maxHeight: 120,
        overflowY: "auto",
      }}
    >
      {filers.map((f) => {
        const active = selectedIds.has(f.id);
        const disabled = !active && selectedIds.size >= MAX_FILERS;
        return (
          <button
            key={f.id}
            onClick={() => onToggle(f.id)}
            disabled={disabled}
            style={{
              padding: "6px 10px",
              fontSize: 11,
              fontWeight: 600,
              background: active ? "var(--accent-cyan)" : "transparent",
              color: active ? "#000" : "var(--accent-cyan)",
              border: `1px solid ${
                disabled ? "var(--border-subtle)" : "var(--accent-cyan)"
              }`,
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.4 : 1,
              transition: "background 0.12s, color 0.12s",
              fontFamily: "monospace",
              fontVariantNumeric: "tabular-nums",
            }}
            title={f.legal_name ?? f.name}
          >
            {f.name}
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------- Compare grid ----------------------------- */

function CellRender({ cell }: { cell: CellInfo | undefined }) {
  if (!cell || !cell.held) {
    return (
      <span
        style={{
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        —
      </span>
    );
  }
  const borderColor =
    cell.direction === "up"
      ? "var(--stock-up)"
      : cell.direction === "down"
        ? "var(--stock-down)"
        : "transparent";
  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: 1,
        padding: "4px 8px",
        border: `1px solid ${borderColor}`,
        background:
          cell.direction === "up"
            ? "color-mix(in srgb, var(--stock-up) 8%, transparent)"
            : cell.direction === "down"
              ? "color-mix(in srgb, var(--stock-down) 8%, transparent)"
              : "transparent",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600 }}>
        {fmtCompact(cell.value)}
      </span>
      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
        {fmtInt(cell.shares)}
      </span>
    </div>
  );
}

/* -------------------------------- Modal -------------------------------- */

export function MultiFilerCompareModal({
  preselectedFilerIds,
  onClose,
}: MultiFilerCompareModalProps) {
  const { data: filers = [] } = useInstitutionalFilers();

  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => {
    const initial = new Set<number>();
    if (preselectedFilerIds) {
      for (const id of preselectedFilerIds.slice(0, MAX_FILERS)) {
        initial.add(id);
      }
    }
    return initial;
  });

  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [onlyCommon, setOnlyCommon] = useState(false);

  /* When the user has made no explicit picks yet, default to the top 2
   * filers by AUM so the modal isn't a blank canvas. Derived (not
   * setState-in-effect) so the rule doesn't fire and we don't pay an
   * extra render to install the default. */
  const effectiveSelectedIds = useMemo<Set<number>>(() => {
    if (selectedIds.size > 0) return selectedIds;
    if (filers.length === 0) return selectedIds;
    const top2 = [...filers]
      .sort(
        (a, b) =>
          (toDecimal(b.latest_total_value_usd) ?? 0) -
          (toDecimal(a.latest_total_value_usd) ?? 0),
      )
      .slice(0, Math.min(2, filers.length))
      .map((f) => f.id);
    return new Set(top2);
  }, [filers, selectedIds]);

  const toggleFiler = (id: number) => {
    // If the user has not made any explicit picks yet, materialise the
    // current derived `effectiveSelectedIds` as the new base before
    // applying the toggle -- otherwise clicking a derived-default chip
    // would *add* it again instead of *removing* it.
    setSelectedIds((prev) => {
      const base = prev.size === 0 ? effectiveSelectedIds : prev;
      const next = new Set(base);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < MAX_FILERS) {
        next.add(id);
      }
      return next;
    });
  };

  const selectedFilers = useMemo(
    () => filers.filter((f) => effectiveSelectedIds.has(f.id)),
    [filers, effectiveSelectedIds],
  );

  /* Fan-out filings list per selected filer. */
  const filingsQueries = useQueries({
    queries: selectedFilers.map((f) => ({
      queryKey: queryKeys.institutional.filings.listByFiler(f.id),
      queryFn: (): Promise<F13Filing[]> => listFilings(f.id),
      enabled: f.id > 0,
      staleTime: 30 * 1000,
    })),
  });

  /* Derive (latest_period, prev_period) per filer. */
  const periodPairs = useMemo<{ latest: string; prev: string | null }[]>(() => {
    return selectedFilers.map((_, i) => {
      const filings = filingsQueries[i]?.data ?? [];
      return {
        latest: filings[0]?.report_period_end ?? "",
        prev: filings[1]?.report_period_end ?? null,
      };
    });
  }, [selectedFilers, filingsQueries]);

  /* Fan-out latest holdings + prev holdings per filer (2N queries). */
  const latestQueries = useQueries({
    queries: selectedFilers.map((f, i) => {
      const period = periodPairs[i]?.latest ?? "";
      return {
        queryKey: queryKeys.institutional.filings.holdings(f.id, period || "latest"),
        queryFn: (): Promise<F13HoldingsAtPeriod> =>
          getHoldings(f.id, period || "latest"),
        enabled: f.id > 0 && period.length > 0,
        staleTime: 60 * 1000,
      };
    }),
  });

  const prevQueries = useQueries({
    queries: selectedFilers.map((f, i) => {
      const period = periodPairs[i]?.prev ?? "";
      return {
        queryKey: queryKeys.institutional.filings.holdings(f.id, period || "__none__"),
        queryFn: (): Promise<F13HoldingsAtPeriod> =>
          getHoldings(f.id, period),
        enabled: f.id > 0 && period.length > 0,
        staleTime: 60 * 1000,
      };
    }),
  });

  /* Compose snapshots. */
  const snapshots = useMemo<FilerSnapshot[]>(() => {
    return selectedFilers.map((f, i) => ({
      filer: f,
      latest: latestQueries[i]?.data ?? null,
      prev: prevQueries[i]?.data ?? null,
      loading:
        (filingsQueries[i]?.isLoading ?? false) ||
        (latestQueries[i]?.isLoading ?? false),
    }));
  }, [selectedFilers, latestQueries, prevQueries, filingsQueries]);

  const anyLoading = snapshots.some((s) => s.loading);

  const rows = useMemo(() => {
    let composed = buildRows(snapshots);
    if (onlyCommon) {
      composed = composed.filter((r) => r.filerCount >= 2);
    }
    composed.sort((a, b) => {
      if (sortKey === "filer_count") {
        if (b.filerCount !== a.filerCount) return b.filerCount - a.filerCount;
        return b.totalValue - a.totalValue;
      }
      return b.totalValue - a.totalValue;
    });
    return composed;
  }, [snapshots, sortKey, onlyCommon]);

  /* Stop background scroll while modal is open. */
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div
      onClick={onClose}
      className="p-0 sm:p-5"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.72)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full h-full sm:h-auto sm:max-h-[calc(100vh-40px)]"
        style={{
          maxWidth: 1200,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <GlassPanel noPadding style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          {/* Header */}
          <div
            style={{
              padding: "14px 18px",
              borderBottom: "1px solid var(--border-subtle)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "var(--bg-secondary)",
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
              <h2
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  margin: 0,
                  color: "var(--foreground)",
                }}
              >
                MULTI-FILER COMPARE
              </h2>
              <span
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                已選 {effectiveSelectedIds.size} / {MAX_FILERS}
              </span>
            </div>
            <ClippedButton variant="cyan-ghost" size="sm" onClick={onClose}>
              關閉
            </ClippedButton>
          </div>

          {/* Controls */}
          <div
            style={{
              padding: 16,
              borderBottom: "1px solid var(--border-subtle)",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div>
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
                選擇 Filer (最多 {MAX_FILERS})
              </div>
              <FilerPicker
                filers={filers}
                selectedIds={effectiveSelectedIds}
                onToggle={toggleFiler}
              />
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                flexWrap: "wrap",
              }}
            >
              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 11,
                  color: "var(--text-secondary)",
                }}
              >
                <span style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  排序
                </span>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  style={{
                    padding: "4px 8px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--foreground)",
                    fontSize: 11,
                    fontFamily: "monospace",
                  }}
                >
                  <option value="value">總價值 (USD)</option>
                  <option value="filer_count">持有 filer 數</option>
                </select>
              </label>

              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 11,
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={onlyCommon}
                  onChange={(e) => setOnlyCommon(e.target.checked)}
                />
                <span>只顯示共同持倉 (≥2 filer)</span>
              </label>

              {anyLoading && (
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    marginLeft: "auto",
                  }}
                >
                  載入中…
                </span>
              )}
            </div>
          </div>

          {/* Grid — let it consume remaining vertical space; flex parent
             caps it. Drop the explicit maxHeight so mobile fullscreen
             modal can scroll the grid all the way to the bottom safe area. */}
          <div style={{ overflow: "auto", flex: 1, minHeight: 0 }}>
            {selectedFilers.length === 0 ? (
              <p
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  textAlign: "center",
                  padding: "40px 0",
                }}
              >
                請至少選擇一個 filer
              </p>
            ) : rows.length === 0 && !anyLoading ? (
              <p
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  textAlign: "center",
                  padding: "40px 0",
                }}
              >
                無共同持倉資料
              </p>
            ) : (
              <table
                style={{
                  width: "100%",
                  fontSize: 12,
                  borderCollapse: "collapse",
                  color: "var(--foreground)",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-color)",
                      background: "var(--bg-secondary)",
                    }}
                  >
                    <th
                      style={{
                        padding: "10px 14px",
                        textAlign: "left",
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        color: "var(--text-muted)",
                        position: "sticky",
                        left: 0,
                        background: "var(--bg-secondary)",
                        zIndex: 2,
                        minWidth: 220,
                      }}
                    >
                      Symbol / Issuer
                    </th>
                    <th
                      style={{
                        padding: "10px 14px",
                        textAlign: "right",
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        color: "var(--text-muted)",
                        minWidth: 80,
                      }}
                    >
                      # Filers
                    </th>
                    {selectedFilers.map((f) => (
                      <th
                        key={f.id}
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontSize: 10,
                          fontWeight: 700,
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                          color: "var(--text-muted)",
                          minWidth: 120,
                          whiteSpace: "nowrap",
                        }}
                        title={f.legal_name ?? f.name}
                      >
                        {f.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.cusip}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                      }}
                    >
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "left",
                          position: "sticky",
                          left: 0,
                          background: "var(--background)",
                          zIndex: 1,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: 2,
                          }}
                        >
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: 13,
                              fontFamily:
                                row.displaySymbol === row.cusip
                                  ? "monospace"
                                  : "inherit",
                            }}
                          >
                            {row.displaySymbol}
                          </span>
                          <span
                            style={{
                              fontSize: 10,
                              color: "var(--text-muted)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              maxWidth: 220,
                              whiteSpace: "nowrap",
                            }}
                            title={row.issuer}
                          >
                            {row.issuer}
                          </span>
                        </div>
                      </td>
                      <td
                        style={{
                          padding: "10px 14px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                          fontWeight:
                            row.filerCount >= 2 ? 700 : 400,
                          color:
                            row.filerCount >= 2
                              ? "var(--accent-cyan)"
                              : "var(--text-secondary)",
                        }}
                      >
                        {row.filerCount}
                      </td>
                      {selectedFilers.map((f) => (
                        <td
                          key={f.id}
                          style={{
                            padding: "8px 14px",
                            textAlign: "right",
                          }}
                        >
                          <CellRender cell={row.cells.get(f.id)} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
