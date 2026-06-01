"use client";

/**
 * BuffettIndicatorTile — slim home-page widget.
 *
 * Renders:  [Ratio % big][label chip][Ⓘ tooltip]
 *
 * Formula tooltip explains:
 *   ratio = 台股總市值 / 台灣 GDP × 100 %
 *   buckets: <50 極度低估 / 50-75 低估 / 75-150 合理 / 150-200 高估 / >200 極度高估
 *
 * Sized to fit a 2-col row of ~80px height (paired with MarketTemperatureTile).
 * Mobile (<lg) drops to stacked rows and is allowed to grow.
 */

import React from "react";
import { useBuffettIndicator } from "@/hooks/use-market-data";
import { InfoTooltip } from "./InfoTooltip";
import type { BuffettLabel } from "@/lib/api-client";

// Label → accent color. Extremes (low/high) go red; middle goes neutral-cyan.
const LABEL_COLOR: Record<BuffettLabel, string> = {
  極度低估: "var(--stock-up)",
  低估: "var(--stock-up)",
  合理: "var(--accent-cyan)",
  高估: "var(--stock-down)",
  極度高估: "var(--stock-down)",
};

const TOOLTIP =
  "巴菲特指標 = 台股總市值 ÷ 台灣 GDP × 100%。<50%極度低估, 50-75%低估, 75-150%合理, 150-200%高估, >200%極度高估。v1 採主計處年度 GDP + 估計市值。";

function BuffettSkeleton() {
  return (
    <div
      style={{
        height: 80,
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderRadius: "var(--glass-radius, 0)",
        backgroundImage: "var(--glass-gradient)",
      }}
    />
  );
}

export function BuffettIndicatorTile() {
  const { data, isLoading } = useBuffettIndicator();

  if (isLoading || !data) return <BuffettSkeleton />;

  const ratio = Number(data.ratio);
  const accent = LABEL_COLOR[data.label] ?? "var(--text-muted)";
  const ratioText = Number.isFinite(ratio) ? `${ratio.toFixed(1)}%` : "—";

  return (
    <div
      style={{
        position: "relative",
        height: 80,
        padding: "10px 14px",
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderLeft: `2px solid ${accent}`,
        borderRadius: "var(--glass-radius, 0)",
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 6,
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}
        >
          Buffett Indicator
        </span>
        <InfoTooltip label={TOOLTIP} ariaLabel="巴菲特指標說明" />
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0 }}>
        <span
          style={{
            fontSize: 26,
            fontWeight: 700,
            lineHeight: 1,
            color: accent,
            fontVariantNumeric: "tabular-nums",
            flexShrink: 0,
          }}
        >
          {ratioText}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            padding: "2px 6px",
            color: accent,
            border: `1px solid ${accent}`,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            flexShrink: 0,
          }}
        >
          {data.label}
        </span>
        {data.historical_extreme && (
          <span
            aria-label="historical extreme"
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              fontStyle: "italic",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minWidth: 0,
            }}
          >
            歷史極端區
          </span>
        )}
      </div>
    </div>
  );
}
