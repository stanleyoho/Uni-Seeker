"use client";

import React, { useId, useMemo } from "react";
import {
  Line,
  Area,
  LineChart as RechartLine,
} from "recharts";
import { GlassPanel } from "./primitives";

// ─── Sparkline ───────────────────────────────────────────────────
interface SparklineProps {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}

export function Sparkline({
  data,
  color = "#10B981",
  width = 80,
  height = 24,
}: SparklineProps) {
  const chartData = useMemo(() => data.map((v) => ({ v })), [data]);

  // Use React's `useId` for a stable, render-pure unique id (Math.random
  // is impure and would violate react-hooks/purity under the Compiler).
  const reactId = useId();
  const gradientId = `spark-${reactId.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <RechartLine width={width} height={height} data={chartData}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <Area
        type="monotone"
        dataKey="v"
        stroke="none"
        fill={`url(#${gradientId})`}
        isAnimationActive={false}
      />
      <Line
        type="monotone"
        dataKey="v"
        stroke={color}
        strokeWidth={1.5}
        dot={(dotProps: Record<string, unknown>) => {
          const index = dotProps.index as number;
          if (index !== data.length - 1) return <React.Fragment key={`no-dot-${index}`} />;
          return (
            <circle
              key={`end-dot-${index}`}
              cx={dotProps.cx as number}
              cy={dotProps.cy as number}
              r={3}
              fill={color}
              stroke="none"
            />
          );
        }}
        isAnimationActive={false}
      />
    </RechartLine>
  );
}

// ─── SectorHeatmap ───────────────────────────────────────────────
interface SectorItem {
  name: string;
  change: string | number;
  marketCap: number;
}

interface SectorHeatmapProps {
  data: SectorItem[];
}

function sectorColor(change: number): string {
  if (change > 0) {
    const intensity = Math.min(change / 3, 1);
    const r = Math.round(16 + intensity * 0);
    const g = Math.round(185 - intensity * 40);
    const b = Math.round(129 - intensity * 50);
    return `rgb(${r}, ${g}, ${b})`;
  }
  const intensity = Math.min(Math.abs(change) / 3, 1);
  const r = Math.round(238 - intensity * 30);
  const g = Math.round(63 + intensity * 10);
  const b = Math.round(44 + intensity * 10);
  return `rgb(${r}, ${g}, ${b})`;
}

export function SectorHeatmap({ data }: SectorHeatmapProps) {
  // Sort descending by marketCap for visual hierarchy
  const sorted = useMemo(
    () => [...data].sort((a, b) => b.marketCap - a.marketCap),
    [data]
  );

  const totalCap = useMemo(
    () => sorted.reduce((s, d) => s + d.marketCap, 0),
    [sorted]
  );

  // Build a simple treemap layout via CSS grid
  // Assign columns based on relative market cap
  return (
    <GlassPanel>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 1,
          background: "#000",
          borderRadius: 6,
          overflow: "hidden",
        }}
      >
        {sorted.map((sector) => {
          const changeVal = typeof sector.change === "string" ? parseFloat(sector.change) : sector.change;
          const fraction = sector.marketCap / totalCap;
          // Larger sectors span 2 columns
          const span = fraction > 0.15 ? 2 : 1;
          return (
            <div
              key={sector.name}
              style={{
                gridColumn: `span ${span}`,
                background: sectorColor(changeVal),
                padding: "10px 8px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "center",
                minHeight: 52,
                cursor: "default",
                transition: "filter 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.filter =
                  "brightness(1.2)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.filter = "none";
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  color: "rgba(255,255,255,0.85)",
                  lineHeight: 1.2,
                }}
              >
                {sector.name}
              </span>
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: "#fff",
                  marginTop: 2,
                }}
              >
                {changeVal > 0 ? "+" : ""}
                {changeVal.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </GlassPanel>
  );
}
