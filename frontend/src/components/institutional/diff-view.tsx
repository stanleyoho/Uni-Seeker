"use client";

/**
 * Diff View — quarter-over-quarter changes for one filer.
 *
 * Tabs: NEW / INCREASED / DECREASED / EXITED. UNCHANGED is intentionally
 * hidden in Phase 2 — it's the "noise" bucket and burying it keeps the
 * UI focused on actionable moves. A future Phase 3 toggle can surface it.
 *
 * Each tab renders a delta-emphasised row: the magnitude of the change
 * is bigger than the absolute values, because the diff is about the
 * gradient, not the snapshot. Color follows TAIWAN convention via the
 * shared `changeTypeColor()` helper.
 *
 * Loading: tab skeleton + 4 row skeletons.
 * Error: inline GlassPanel with the raw API error message.
 * Empty (a tab has zero rows): "本期無此類異動".
 */

import { useMemo, useState } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { useDiff } from "@/hooks/use-institutional";
import { ApiError } from "@/lib/api-client";
import {
  changeTypeColor,
  changeTypeLabel,
  fmtCompact,
  fmtInt,
  fmtPct,
  toDecimal,
  type F13ChangeType,
  type F13HoldingChange,
} from "./types";

export interface DiffViewProps {
  filerId: number;
  /** ISO date of the previous quarter (must match a stored filing). */
  fromDate: string;
  /** ISO date of the current quarter. */
  toDate: string;
}

const TABS: F13ChangeType[] = ["NEW", "INCREASED", "DECREASED", "EXITED"];

function mapDiffError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "載入失敗";
  }
  if (err.status === 404) {
    return "缺少對應期間的 filing — 請先 refresh 拉資料";
  }
  return err.message || "載入失敗";
}

interface DerivedChange {
  raw: F13HoldingChange;
  delta_shares: number;
  delta_pct: number | null;
  delta_value: number;
  prev_value: number | null;
  curr_value: number | null;
}

function derive(c: F13HoldingChange): DerivedChange {
  return {
    raw: c,
    delta_shares: toDecimal(c.delta_shares) ?? 0,
    delta_pct: toDecimal(c.delta_pct),
    delta_value: toDecimal(c.delta_value_usd) ?? 0,
    prev_value: toDecimal(c.prev_value_usd),
    curr_value: toDecimal(c.curr_value_usd),
  };
}

interface TabButtonProps {
  type: F13ChangeType;
  active: boolean;
  count: number;
  onClick: () => void;
}

function TabButton({ type, active, count, onClick }: TabButtonProps) {
  const color = changeTypeColor(type);
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: "10px 12px",
        fontSize: 11,
        fontWeight: 700,
        background: active ? color : "transparent",
        color: active ? "#fff" : color,
        border: `1px solid ${color}`,
        cursor: "pointer",
        transition: "background 0.15s, color 0.15s",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
      }}
    >
      <span>{changeTypeLabel(type)}</span>
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          opacity: 0.8,
        }}
      >
        {count}
      </span>
    </button>
  );
}

function ChangeRow({ change }: { change: DerivedChange }) {
  const color = changeTypeColor(change.raw.change_type);

  // Delta is the headline; absolute values support context. For NEW the
  // headline is the curr_value (there's no prev). For EXITED the headline
  // is the |prev_value| (there's no curr). For INC/DEC we show signed
  // delta_value and percent.
  let headline: string;
  let subline: string;
  switch (change.raw.change_type) {
    case "NEW":
      headline = fmtCompact(change.curr_value ?? change.delta_value);
      subline = `新進 ${fmtInt(toDecimal(change.raw.curr_shares))} 股`;
      break;
    case "EXITED":
      headline = `−${fmtCompact(Math.abs(change.prev_value ?? change.delta_value))}`;
      subline = `清空 ${fmtInt(toDecimal(change.raw.prev_shares))} 股`;
      break;
    case "INCREASED":
      headline = `+${fmtCompact(Math.abs(change.delta_value))}`;
      subline = `${fmtPct(change.delta_pct)} · ${fmtInt(toDecimal(change.raw.prev_shares))} → ${fmtInt(toDecimal(change.raw.curr_shares))}`;
      break;
    case "DECREASED":
      headline = `−${fmtCompact(Math.abs(change.delta_value))}`;
      subline = `${fmtPct(change.delta_pct)} · ${fmtInt(toDecimal(change.raw.prev_shares))} → ${fmtInt(toDecimal(change.raw.curr_shares))}`;
      break;
    default:
      headline = fmtCompact(change.delta_value);
      subline = fmtPct(change.delta_pct);
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 14px",
        borderBottom: "1px solid var(--border-subtle)",
        gap: 16,
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
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            fontWeight: 700,
            color: "var(--foreground)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {change.raw.cusip}
        </span>
        <span
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={change.raw.name_of_issuer}
        >
          {change.raw.name_of_issuer}
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
            fontSize: 15,
            fontWeight: 700,
            color,
          }}
        >
          {headline}
        </span>
        <span
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          {subline}
        </span>
      </div>
    </div>
  );
}

export function DiffView({ filerId, fromDate, toDate }: DiffViewProps) {
  const [activeTab, setActiveTab] = useState<F13ChangeType>("NEW");

  const queryReady = fromDate.length > 0 && toDate.length > 0;
  const { data, isLoading, error } = useDiff(
    queryReady ? filerId : null,
    fromDate,
    toDate,
  );

  /* Bucketise + pre-derive per tab. */
  const buckets = useMemo(() => {
    const init: Record<F13ChangeType, DerivedChange[]> = {
      NEW: [],
      INCREASED: [],
      DECREASED: [],
      EXITED: [],
      UNCHANGED: [],
    };
    if (!data) return init;
    for (const change of data.changes) {
      const ct = change.change_type as F13ChangeType;
      if (init[ct]) init[ct].push(derive(change));
    }
    // Order each bucket by |delta_value| desc — the biggest moves first.
    for (const ct of TABS) {
      init[ct].sort(
        (a, b) => Math.abs(b.delta_value) - Math.abs(a.delta_value),
      );
    }
    return init;
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
          選擇兩個期間以查看季度異動
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

  const activeRows = buckets[activeTab];

  return (
    <GlassPanel noPadding>
      {/* Period summary */}
      <div
        style={{
          padding: "10px 14px",
          fontSize: 11,
          color: "var(--text-muted)",
          background: "var(--bg-secondary)",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: 12,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span style={{ fontWeight: 700, letterSpacing: "0.05em" }}>
          QOQ DIFF
        </span>
        <span>
          {fromDate}{" "}
          <span style={{ color: "var(--accent-cyan)" }}>→</span> {toDate}
        </span>
        {data && (
          <span style={{ marginLeft: "auto" }}>
            共 {data.changes.length} 筆變動
          </span>
        )}
      </div>

      {/* Tab strip */}
      <div
        style={{
          display: "flex",
          gap: 6,
          padding: 14,
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        {TABS.map((t) => (
          <TabButton
            key={t}
            type={t}
            active={activeTab === t}
            count={buckets[t].length}
            onClick={() => setActiveTab(t)}
          />
        ))}
      </div>

      {/* Rows */}
      <div style={{ maxHeight: 480, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: "space-between",
                padding: "12px 14px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <div
                style={{
                  height: 32,
                  background: "var(--card-hover)",
                  width: 180,
                }}
              />
              <div
                style={{
                  height: 32,
                  background: "var(--card-hover)",
                  width: 100,
                }}
              />
            </div>
          ))
        ) : activeRows.length === 0 ? (
          <p
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              textAlign: "center",
              padding: "32px 0",
            }}
          >
            本期無此類異動
          </p>
        ) : (
          activeRows.map((c) => <ChangeRow key={c.raw.cusip} change={c} />)
        )}
      </div>
    </GlassPanel>
  );
}
