"use client";

/**
 * MarketTemperatureTile — gradient gauge widget for the home page.
 *
 * Renders:  [emoji][cold-blue → hot-red bar with needle][label chip][Ⓘ]
 *
 * Sits next to BuffettIndicatorTile in the 2-col macro row (~80px tall on lg).
 *
 * Score is a 0-100 number from the backend; we render the needle at
 * `score%` along a 1-D gradient bar. The gauge stays purely CSS — no
 * SVG arc — so the height budget stays compact and the bar reads quickly.
 */

import React from "react";
import { useMarketTemperature } from "@/hooks/use-market-data";
import { InfoTooltip } from "./InfoTooltip";
import type { TemperatureLabel } from "@/lib/api-client";

const LABEL_EMOJI: Record<TemperatureLabel, string> = {
  冷: "🥶",
  正常: "😐",
  熱: "🔥",
};

const LABEL_COLOR: Record<TemperatureLabel, string> = {
  冷: "var(--accent-cyan)",
  正常: "var(--text-muted)",
  熱: "var(--stock-down)",
};

const TOOLTIP =
  "市場溫度 = 指數籃子今日平均漲跌幅。≤-1% 冷, -1~+1% 正常, ≥+1% 熱。score 0-100 線性對應 [-3%, +3%]。v2 將加入 RSI / 漲跌家數 / 量能。";

function TemperatureSkeleton() {
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

export function MarketTemperatureTile() {
  const { data, isLoading } = useMarketTemperature();

  if (isLoading || !data) return <TemperatureSkeleton />;

  const score = Number(data.score);
  const avgPct = Number(data.average_change_percent);
  // Clamp needle position into [2, 98] so it never touches the bar edges
  // (avoids the visual impression that the needle is "off").
  const needlePct = Number.isFinite(score) ? Math.max(2, Math.min(98, score)) : 50;
  const accent = LABEL_COLOR[data.label] ?? "var(--text-muted)";

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
          Market Temperature
        </span>
        <InfoTooltip label={TOOLTIP} ariaLabel="市場溫度說明" />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          aria-hidden="true"
          style={{ fontSize: 22, lineHeight: 1, flexShrink: 0 }}
        >
          {LABEL_EMOJI[data.label]}
        </span>

        {/* Gradient bar with needle. The bar is cold-blue → warm-red so the
            user reads left = cold, right = hot at a glance. */}
        <div
          style={{
            position: "relative",
            flex: 1,
            height: 10,
            background:
              "linear-gradient(90deg, #38bdf8 0%, #94a3b8 50%, #ef4444 100%)",
            borderRadius: 6,
            overflow: "visible",
          }}
          role="meter"
          aria-label="市場溫度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Number.isFinite(score) ? score : 50}
          aria-valuetext={`${data.label} (${avgPct.toFixed(2)}%)`}
        >
          {/* Needle */}
          <div
            style={{
              position: "absolute",
              left: `${needlePct}%`,
              top: -3,
              width: 2,
              height: 16,
              background: "var(--foreground, #fff)",
              transform: "translateX(-50%)",
              boxShadow: "0 0 4px rgba(0,0,0,0.7)",
            }}
          />
        </div>

        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            padding: "2px 6px",
            color: accent,
            border: `1px solid ${accent}`,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontVariantNumeric: "tabular-nums",
            flexShrink: 0,
          }}
        >
          {data.label} {Number.isFinite(avgPct) ? `${avgPct >= 0 ? "+" : ""}${avgPct.toFixed(2)}%` : ""}
        </span>
      </div>
    </div>
  );
}
