"use client";

import React, { useMemo, useState } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Area,
  LineChart as RechartLine,
  AreaChart,
} from "recharts";
import { GlassPanel } from "./primitives";
import type { OHLCV, SECTORS } from "./mock-data";

// ─── Timeframe / overlay constants ───────────────────────────────
const TIMEFRAMES = ["1D", "5D", "1M", "6M", "1Y", "5Y", "ALL"] as const;
const OVERLAYS = ["MA20", "MA50", "RSI", "Volume"] as const;

// ─── Helpers ─────────────────────────────────────────────────────
function computeMA(data: OHLCV[], period: number): (number | null)[] {
  return data.map((_, i) => {
    if (i < period - 1) return null;
    const slice = data.slice(i - period + 1, i + 1);
    return parseFloat(
      (slice.reduce((s, d) => s + d.close, 0) / period).toFixed(2)
    );
  });
}

// ─── Custom candlestick shape ────────────────────────────────────
interface CandlestickProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: OHLCV;
  yAxis?: { scale: (v: number) => number };
}

function CandlestickShape(props: CandlestickProps) {
  const { x = 0, width = 0, payload, yAxis } = props;
  if (!payload || !yAxis?.scale) return null;

  const { open, close, high, low } = payload;
  const bullish = close >= open;
  const color = bullish ? "#10B981" : "#EE3F2C";

  const yOpen = yAxis.scale(open);
  const yClose = yAxis.scale(close);
  const yHigh = yAxis.scale(high);
  const yLow = yAxis.scale(low);

  const bodyTop = Math.min(yOpen, yClose);
  const bodyHeight = Math.max(Math.abs(yOpen - yClose), 1);
  const center = x + width / 2;

  return (
    <g>
      {/* Upper wick */}
      <line
        x1={center}
        y1={yHigh}
        x2={center}
        y2={bodyTop}
        stroke={color}
        strokeWidth={1}
      />
      {/* Lower wick */}
      <line
        x1={center}
        y1={bodyTop + bodyHeight}
        x2={center}
        y2={yLow}
        stroke={color}
        strokeWidth={1}
      />
      {/* Body */}
      <rect
        x={x + 1}
        y={bodyTop}
        width={Math.max(width - 2, 2)}
        height={bodyHeight}
        fill={color}
      />
    </g>
  );
}

// ─── PrimaryChart ────────────────────────────────────────────────
interface PrimaryChartProps {
  symbol: string;
  data: OHLCV[];
}

export function PrimaryChart({ symbol, data }: PrimaryChartProps) {
  const [activeTimeframe, setActiveTimeframe] = useState<string>("1D");
  const [activeOverlays, setActiveOverlays] = useState<Set<string>>(
    new Set(["Volume"])
  );

  const toggleOverlay = (o: string) => {
    setActiveOverlays((prev) => {
      const next = new Set(prev);
      if (next.has(o)) next.delete(o);
      else next.add(o);
      return next;
    });
  };

  // Pre-compute moving averages
  const ma20 = useMemo(() => computeMA(data, 20), [data]);
  const ma50 = useMemo(() => computeMA(data, 50), [data]);

  // Merge MAs into chart data
  const chartData = useMemo(
    () =>
      data.map((d, i) => ({
        ...d,
        ma20: ma20[i],
        ma50: ma50[i],
      })),
    [data, ma20, ma50]
  );

  // Y-axis domain from price range
  const [yMin, yMax] = useMemo(() => {
    let lo = Infinity;
    let hi = -Infinity;
    for (const d of data) {
      if (d.low < lo) lo = d.low;
      if (d.high > hi) hi = d.high;
    }
    const pad = (hi - lo) * 0.05;
    return [parseFloat((lo - pad).toFixed(2)), parseFloat((hi + pad).toFixed(2))];
  }, [data]);

  const maxVolume = useMemo(
    () => Math.max(...data.map((d) => d.volume)),
    [data]
  );

  return (
    <GlassPanel>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        {/* Timeframe tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setActiveTimeframe(tf)}
              style={{
                padding: "3px 10px",
                fontSize: 11,
                fontWeight: 500,
                borderRadius: 4,
                border: "1px solid rgba(255,255,255,0.12)",
                background:
                  activeTimeframe === tf
                    ? "rgba(255,255,255,1)"
                    : "transparent",
                color: activeTimeframe === tf ? "#000" : "rgba(255,255,255,0.6)",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Overlay toggles */}
        <div style={{ display: "flex", gap: 4 }}>
          {OVERLAYS.map((o) => {
            const active = activeOverlays.has(o);
            return (
              <button
                key={o}
                onClick={() => toggleOverlay(o)}
                style={{
                  padding: "3px 8px",
                  fontSize: 10,
                  fontWeight: 500,
                  borderRadius: 10,
                  border: active
                    ? "1px solid rgba(255,255,255,0.3)"
                    : "1px solid rgba(255,255,255,0.08)",
                  background: active
                    ? "rgba(255,255,255,0.12)"
                    : "transparent",
                  color: active
                    ? "rgba(255,255,255,0.9)"
                    : "rgba(255,255,255,0.4)",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {o}
              </button>
            );
          })}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart
          data={chartData}
          margin={{ top: 4, right: 8, bottom: 4, left: 4 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(255,255,255,0.04)"
          />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.4)" }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(data.length / 6)}
          />
          <YAxis
            yAxisId="price"
            domain={[yMin, yMax]}
            tick={{ fontSize: 11, fill: "rgba(255,255,255,0.4)" }}
            tickLine={false}
            axisLine={false}
            orientation="right"
            width={60}
          />
          {activeOverlays.has("Volume") && (
            <YAxis
              yAxisId="volume"
              domain={[0, maxVolume * 5]}
              hide
              orientation="left"
            />
          )}
          <Tooltip
            contentStyle={{
              background: "rgba(0,0,0,0.85)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 6,
              fontSize: 11,
              color: "#fff",
            }}
          />

          {/* Volume bars */}
          {activeOverlays.has("Volume") && (
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill="rgba(255,255,255,0.08)"
              isAnimationActive={false}
            />
          )}

          {/* Candlestick via Bar with custom shape */}
          <Bar
            yAxisId="price"
            dataKey="high"
            /* eslint-disable @typescript-eslint/no-explicit-any */
            shape={(props: any) => {
              const yAxisScale = props.yAxis as
                | { scale: (v: number) => number }
                | undefined;
              return (
                <CandlestickShape
                  x={props.x as number}
                  y={props.y as number}
                  width={props.width as number}
                  height={props.height as number}
                  payload={props.payload as OHLCV}
                  yAxis={yAxisScale}
                />
              );
            }}
            /* eslint-enable @typescript-eslint/no-explicit-any */
            isAnimationActive={false}
          />

          {/* MA overlays */}
          {activeOverlays.has("MA20") && (
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="ma20"
              stroke="#FBBF24"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
          {activeOverlays.has("MA50") && (
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="ma50"
              stroke="#818CF8"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </GlassPanel>
  );
}

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

  const gradientId = useMemo(
    () => `spark-${Math.random().toString(36).slice(2, 8)}`,
    []
  );

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
type SectorData = typeof SECTORS;

interface SectorHeatmapProps {
  data: SectorData;
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
          const fraction = sector.marketCap / totalCap;
          // Larger sectors span 2 columns
          const span = fraction > 0.15 ? 2 : 1;
          return (
            <div
              key={sector.name}
              style={{
                gridColumn: `span ${span}`,
                background: sectorColor(sector.change),
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
                {sector.change > 0 ? "+" : ""}
                {sector.change.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </GlassPanel>
  );
}
