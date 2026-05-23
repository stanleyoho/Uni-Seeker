"use client";

/**
 * Filer List Card — Phase 7 mobile-first redesign.
 *
 * Card-per-row alternative to `filer-list.tsx`. Same props
 * (`FilerListProps`). Each subscribed filer renders as a card:
 *
 *   ┌──────────────────────────────────────────────┐
 *   │ Berkshire Hathaway Inc                       │  ← name (large)
 *   │ Berkshire Hathaway Inc. (DE)        ·  CIK 0001067983 │  ← legal name + cik (small)
 *   │ AUM $355.6B    Positions 47    Filed 2025-09-30       │  ← stats grid
 *   └──────────────────────────────────────────────┘
 *
 * Visual rules:
 *   - Selected card → `var(--card-active)` background + cyan left border.
 *   - Tapping fires `onSelect(filerId)`; cards are full-width buttons
 *     with proper role + Enter/Space key support for accessibility.
 *   - 4-row card targets ~96 px min-height for comfortable thumb tap.
 *   - Empty-state matches the desktop `FilerList`.
 */

import { useMemo } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { fmtCompact, fmtInt, toDecimal, type F13Filer } from "./types";
import type { FilerListProps } from "./filer-list";

interface DerivedRow {
  raw: F13Filer;
  total_value: number | null;
  position_count: number | null;
}

function SkeletonCard() {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--border-subtle)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minHeight: 96,
      }}
    >
      <div
        style={{
          height: 14,
          background: "var(--card-hover)",
          width: "55%",
        }}
      />
      <div
        style={{
          height: 11,
          background: "var(--card-hover)",
          width: "80%",
        }}
      />
      <div
        style={{
          height: 12,
          background: "var(--card-hover)",
          width: "70%",
        }}
      />
    </div>
  );
}

export function FilerListCard({
  filers,
  selectedFilerId,
  onSelect,
  loading = false,
  emptyCta,
}: FilerListProps) {
  // Sort desc by AUM by default (matches desktop FilerList default sort).
  const rows = useMemo<DerivedRow[]>(() => {
    const derived = filers.map((f) => ({
      raw: f,
      total_value: toDecimal(f.latest_total_value_usd),
      position_count: f.latest_position_count,
    }));
    derived.sort(
      (a, b) =>
        (b.total_value ?? Number.NEGATIVE_INFINITY) -
        (a.total_value ?? Number.NEGATIVE_INFINITY),
    );
    return derived;
  }, [filers]);

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
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          color: "var(--foreground)",
        }}
      >
        {loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <li key={i}>
                <SkeletonCard />
              </li>
            ))
          : rows.map((r) => {
              const sel = selectedFilerId === r.raw.id;
              return (
                <li
                  key={r.raw.id}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(r.raw.id)}
                    aria-pressed={sel}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "14px 16px",
                      // Left accent border for selected — visual emphasis
                      // that survives small viewports without a checkbox.
                      borderLeft: sel
                        ? "3px solid var(--accent-cyan)"
                        : "3px solid transparent",
                      background: sel
                        ? "var(--card-active)"
                        : "transparent",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                      minHeight: 96,
                      color: "inherit",
                      font: "inherit",
                      transition: "background 0.12s",
                    }}
                  >
                    {/* Name */}
                    <span
                      style={{
                        fontSize: 15,
                        fontWeight: 700,
                        color: "var(--foreground)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={r.raw.name}
                    >
                      {r.raw.name}
                    </span>

                    {/* Legal name + CIK */}
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 10,
                        color: "var(--text-muted)",
                      }}
                    >
                      {r.raw.legal_name && r.raw.legal_name !== r.raw.name && (
                        <span
                          style={{
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            maxWidth: "60%",
                          }}
                          title={r.raw.legal_name}
                        >
                          {r.raw.legal_name}
                        </span>
                      )}
                      <span
                        style={{
                          fontFamily: "monospace",
                          fontVariantNumeric: "tabular-nums",
                          letterSpacing: "0.04em",
                        }}
                      >
                        CIK {r.raw.cik}
                      </span>
                    </div>

                    {/* Stats grid: AUM / Positions / Filed */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr 1fr",
                        gap: 12,
                        marginTop: 2,
                      }}
                    >
                      <CardStat
                        label="13F AUM"
                        value={fmtCompact(r.total_value)}
                        emphasis
                      />
                      <CardStat
                        label="Positions"
                        value={fmtInt(r.position_count)}
                      />
                      <CardStat
                        label="Filed"
                        value={r.raw.latest_filing_date ?? "—"}
                        muted={!r.raw.latest_filing_date}
                        align="right"
                      />
                    </div>
                  </button>
                </li>
              );
            })}
      </ul>
    </GlassPanel>
  );
}

function CardStat({
  label,
  value,
  emphasis = false,
  muted = false,
  align = "left",
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  muted?: boolean;
  align?: "left" | "right";
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 2,
        alignItems: align === "right" ? "flex-end" : "flex-start",
        minWidth: 0,
      }}
    >
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 12,
          fontWeight: emphasis ? 700 : 600,
          fontVariantNumeric: "tabular-nums",
          color: muted ? "var(--text-muted)" : "var(--foreground)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          maxWidth: "100%",
        }}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}
