"use client";

import { useState, useMemo, useCallback } from "react";
import type { StockPrice } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface IndicatorPanelProps {
  prices: StockPrice[];
  t: Record<string, any>;
}

interface IndicatorConfig {
  key: string;
  label: string;
  enabled: boolean;
  params: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Calculation helpers
// ---------------------------------------------------------------------------

function ema(data: number[], period: number): number[] {
  const result: number[] = [];
  const k = 2 / (period + 1);
  let prev = data[0];
  result.push(prev);
  for (let i = 1; i < data.length; i++) {
    prev = data[i] * k + prev * (1 - k);
    result.push(prev);
  }
  return result;
}

function calcRSI(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  if (closes.length < period + 1) return closes.map(() => null);

  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) avgGain += diff;
    else avgLoss -= diff;
  }
  avgGain /= period;
  avgLoss /= period;

  for (let i = 0; i < period; i++) result.push(null);

  const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  result.push(100 - 100 / (1 + rs));

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const r = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push(100 - 100 / (1 + r));
  }
  return result;
}

function calcMACD(
  closes: number[],
  fast: number,
  slow: number,
  signal: number,
): { macd: (number | null)[]; signal: (number | null)[]; histogram: (number | null)[] } {
  if (closes.length < slow) {
    const n = closes.map(() => null);
    return { macd: n, signal: n, histogram: n };
  }
  const fastEma = ema(closes, fast);
  const slowEma = ema(closes, slow);
  const macdLine = fastEma.map((f, i) => f - slowEma[i]);
  const signalLine = ema(macdLine, signal);
  const hist = macdLine.map((m, i) => m - signalLine[i]);

  // Null out the warm-up period
  const result = {
    macd: macdLine.map((v, i) => (i < slow - 1 ? null : v)),
    signal: signalLine.map((v, i) => (i < slow + signal - 2 ? null : v)),
    histogram: hist.map((v, i) => (i < slow + signal - 2 ? null : v)),
  };
  return result;
}

function calcKD(
  highs: number[],
  lows: number[],
  closes: number[],
  period: number,
): { k: (number | null)[]; d: (number | null)[] } {
  const n = closes.length;
  const rsv: (number | null)[] = [];

  for (let i = 0; i < n; i++) {
    if (i < period - 1) {
      rsv.push(null);
      continue;
    }
    let hh = -Infinity;
    let ll = Infinity;
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hh) hh = highs[j];
      if (lows[j] < ll) ll = lows[j];
    }
    const range = hh - ll;
    rsv.push(range === 0 ? 50 : ((closes[i] - ll) / range) * 100);
  }

  const k: (number | null)[] = [];
  const d: (number | null)[] = [];
  let prevK = 50;
  let prevD = 50;

  for (let i = 0; i < n; i++) {
    if (rsv[i] === null) {
      k.push(null);
      d.push(null);
    } else {
      prevK = (2 / 3) * prevK + (1 / 3) * rsv[i]!;
      prevD = (2 / 3) * prevD + (1 / 3) * prevK;
      k.push(prevK);
      d.push(prevD);
    }
  }
  return { k, d };
}

function calcBias(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
      continue;
    }
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += closes[j];
    const ma = sum / period;
    result.push(ma === 0 ? 0 : ((closes[i] - ma) / ma) * 100);
  }
  return result;
}

// ---------------------------------------------------------------------------
// SVG mini-chart renderers
// ---------------------------------------------------------------------------

const CHART_HEIGHT = 150;
const CHART_PADDING = { top: 12, right: 48, bottom: 20, left: 8 };

function usableWidth(w: number) {
  return w - CHART_PADDING.left - CHART_PADDING.right;
}
function usableHeight() {
  return CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
}

/** Map a value to y coordinate within the chart area */
function yScale(value: number, min: number, max: number): number {
  const range = max - min || 1;
  return CHART_PADDING.top + usableHeight() * (1 - (value - min) / range);
}

/** Build an SVG path from data points */
function buildPath(
  data: (number | null)[],
  min: number,
  max: number,
  totalWidth: number,
): string {
  const w = usableWidth(totalWidth);
  const parts: string[] = [];
  let started = false;
  const count = data.length;

  for (let i = 0; i < count; i++) {
    const v = data[i];
    if (v === null) {
      started = false;
      continue;
    }
    const x = CHART_PADDING.left + (i / (count - 1)) * w;
    const y = yScale(v, min, max);
    parts.push(`${started ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`);
    started = true;
  }
  return parts.join(" ");
}

/** Format axis labels */
function fmtLabel(v: number): string {
  if (Math.abs(v) >= 1000) return v.toFixed(0);
  if (Math.abs(v) >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

/** Y-axis ticks */
function YAxis({ min, max, ticks, totalWidth }: { min: number; max: number; ticks: number[]; totalWidth: number }) {
  return (
    <>
      {ticks.map((v) => {
        const y = yScale(v, min, max);
        return (
          <g key={v}>
            <line
              x1={CHART_PADDING.left}
              x2={totalWidth - CHART_PADDING.right}
              y1={y}
              y2={y}
              stroke="var(--border-subtle)"
              strokeWidth={0.5}
            />
            <text
              x={totalWidth - CHART_PADDING.right + 4}
              y={y + 3}
              fill="var(--text-muted)"
              fontSize={9}
              fontFamily="monospace"
            >
              {fmtLabel(v)}
            </text>
          </g>
        );
      })}
    </>
  );
}

/** Horizontal reference line (e.g. 0-line, overbought/oversold) */
function RefLine({
  value,
  min,
  max,
  totalWidth,
  color,
  dashed,
}: {
  value: number;
  min: number;
  max: number;
  totalWidth: number;
  color: string;
  dashed?: boolean;
}) {
  const y = yScale(value, min, max);
  return (
    <line
      x1={CHART_PADDING.left}
      x2={totalWidth - CHART_PADDING.right}
      y1={y}
      y2={y}
      stroke={color}
      strokeWidth={0.5}
      strokeDasharray={dashed ? "4 3" : undefined}
      opacity={0.5}
    />
  );
}

// ---------------------------------------------------------------------------
// Individual indicator charts
// ---------------------------------------------------------------------------

function RSIChart({ data, width }: { data: (number | null)[]; width: number }) {
  const min = 0;
  const max = 100;
  const ticks = [0, 30, 50, 70, 100];
  const path = buildPath(data, min, max, width);

  // Zone fills for overbought/oversold
  const y70 = yScale(70, min, max);
  const y30 = yScale(30, min, max);

  return (
    <svg width={width} height={CHART_HEIGHT} className="block">
      {/* Overbought zone */}
      <rect
        x={CHART_PADDING.left}
        y={CHART_PADDING.top}
        width={usableWidth(width)}
        height={y70 - CHART_PADDING.top}
        fill="rgba(239, 68, 68, 0.06)"
      />
      {/* Oversold zone */}
      <rect
        x={CHART_PADDING.left}
        y={y30}
        width={usableWidth(width)}
        height={CHART_PADDING.top + usableHeight() - y30}
        fill="rgba(34, 197, 94, 0.06)"
      />
      <YAxis min={min} max={max} ticks={ticks} totalWidth={width} />
      <RefLine value={70} min={min} max={max} totalWidth={width} color="#ef4444" dashed />
      <RefLine value={30} min={min} max={max} totalWidth={width} color="#22c55e" dashed />
      <path d={path} fill="none" stroke="#22c55e" strokeWidth={1.5} />
    </svg>
  );
}

function MACDChart({
  macd,
  signal,
  histogram,
  width,
}: {
  macd: (number | null)[];
  signal: (number | null)[];
  histogram: (number | null)[];
  width: number;
}) {
  const allValues = [...macd, ...signal, ...histogram].filter((v): v is number => v !== null);
  if (allValues.length === 0) return null;
  const absMax = Math.max(...allValues.map(Math.abs), 0.01);
  const min = -absMax;
  const max = absMax;
  const ticks = [-absMax, 0, absMax];

  const w = usableWidth(width);
  const count = histogram.length;
  const barW = Math.max(1, w / count - 0.5);

  return (
    <svg width={width} height={CHART_HEIGHT} className="block">
      <YAxis min={min} max={max} ticks={ticks} totalWidth={width} />
      <RefLine value={0} min={min} max={max} totalWidth={width} color="var(--text-muted)" dashed />
      {/* Histogram bars */}
      {histogram.map((v, i) => {
        if (v === null) return null;
        const x = CHART_PADDING.left + (i / (count - 1)) * w - barW / 2;
        const zeroY = yScale(0, min, max);
        const valY = yScale(v, min, max);
        const barH = Math.abs(valY - zeroY) || 0.5;
        return (
          <rect
            key={i}
            x={x}
            y={v >= 0 ? valY : zeroY}
            width={barW}
            height={barH}
            fill={v >= 0 ? "rgba(34, 197, 94, 0.7)" : "rgba(239, 68, 68, 0.7)"}
          />
        );
      })}
      {/* MACD line */}
      <path d={buildPath(macd, min, max, width)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
      {/* Signal line */}
      <path d={buildPath(signal, min, max, width)} fill="none" stroke="#f97316" strokeWidth={1.5} />
    </svg>
  );
}

function KDChart({ k, d, width }: { k: (number | null)[]; d: (number | null)[]; width: number }) {
  const min = 0;
  const max = 100;
  const ticks = [0, 20, 50, 80, 100];

  return (
    <svg width={width} height={CHART_HEIGHT} className="block">
      <YAxis min={min} max={max} ticks={ticks} totalWidth={width} />
      <RefLine value={80} min={min} max={max} totalWidth={width} color="#ef4444" dashed />
      <RefLine value={20} min={min} max={max} totalWidth={width} color="#22c55e" dashed />
      <path d={buildPath(k, min, max, width)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
      <path d={buildPath(d, min, max, width)} fill="none" stroke="#f97316" strokeWidth={1.5} />
    </svg>
  );
}

function BiasChart({ data, width }: { data: (number | null)[]; width: number }) {
  const values = data.filter((v): v is number => v !== null);
  if (values.length === 0) return null;
  const absMax = Math.max(...values.map(Math.abs), 1);
  const min = -absMax;
  const max = absMax;
  const ticks = [-absMax, 0, absMax];

  return (
    <svg width={width} height={CHART_HEIGHT} className="block">
      <YAxis min={min} max={max} ticks={ticks} totalWidth={width} />
      <RefLine value={0} min={min} max={max} totalWidth={width} color="var(--text-muted)" dashed />
      <path d={buildPath(data, min, max, width)} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

const DEFAULT_CONFIGS: IndicatorConfig[] = [
  { key: "rsi", label: "RSI", enabled: true, params: { period: 14 } },
  { key: "macd", label: "MACD", enabled: true, params: { fast: 12, slow: 26, signal: 9 } },
  { key: "kd", label: "KD", enabled: false, params: { period: 9 } },
  { key: "bias", label: "BIAS", enabled: false, params: { period: 20 } },
];

export function IndicatorPanel({ prices, t }: IndicatorPanelProps) {
  const [configs, setConfigs] = useState<IndicatorConfig[]>(DEFAULT_CONFIGS);
  const [showParams, setShowParams] = useState(false);

  const toggleIndicator = useCallback((key: string) => {
    setConfigs((prev) =>
      prev.map((c) => (c.key === key ? { ...c, enabled: !c.enabled } : c)),
    );
  }, []);

  const updateParam = useCallback((key: string, param: string, value: number) => {
    setConfigs((prev) =>
      prev.map((c) =>
        c.key === key ? { ...c, params: { ...c.params, [param]: value } } : c,
      ),
    );
  }, []);

  // Parse and sort prices once
  const parsed = useMemo(() => {
    const sorted = [...prices].sort((a, b) => a.date.localeCompare(b.date));
    return sorted.map((p) => ({
      date: p.date,
      open: parseFloat(p.open),
      high: parseFloat(p.high),
      low: parseFloat(p.low),
      close: parseFloat(p.close),
    }));
  }, [prices]);

  const closes = useMemo(() => parsed.map((p) => p.close), [parsed]);
  const highs = useMemo(() => parsed.map((p) => p.high), [parsed]);
  const lows = useMemo(() => parsed.map((p) => p.low), [parsed]);

  // Calculate indicators
  const indicators = useMemo(() => {
    const cfgMap = Object.fromEntries(configs.map((c) => [c.key, c]));

    return {
      rsi: cfgMap.rsi.enabled ? calcRSI(closes, cfgMap.rsi.params.period) : null,
      macd: cfgMap.macd.enabled
        ? calcMACD(closes, cfgMap.macd.params.fast, cfgMap.macd.params.slow, cfgMap.macd.params.signal)
        : null,
      kd: cfgMap.kd.enabled ? calcKD(highs, lows, closes, cfgMap.kd.params.period) : null,
      bias: cfgMap.bias.enabled ? calcBias(closes, cfgMap.bias.params.period) : null,
    };
  }, [closes, highs, lows, configs]);

  const s = t.stock ?? {};
  const ind = t.indicators ?? {};

  if (parsed.length < 2) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--text-muted)] text-sm">{s.noData ?? "No data"}</p>
      </div>
    );
  }

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 space-y-3">
      {/* Header with toggles */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
          {ind.title ?? "Technical Indicators"}
        </h3>
        <button
          onClick={() => setShowParams((p) => !p)}
          className="text-[10px] text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors"
          aria-expanded={showParams}
          aria-label={ind.paramToggle ?? "Toggle parameters"}
        >
          {showParams ? (ind.hideParams ?? "Hide Params") : (ind.showParams ?? "Params")}
        </button>
      </div>

      {/* Indicator checkboxes */}
      <div className="flex flex-wrap gap-2" role="group" aria-label={ind.selectIndicators ?? "Select indicators"}>
        {configs.map((cfg) => (
          <label
            key={cfg.key}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium cursor-pointer transition-all duration-200 select-none border ${
              cfg.enabled
                ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 text-[var(--accent-blue)]"
                : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            <input
              type="checkbox"
              checked={cfg.enabled}
              onChange={() => toggleIndicator(cfg.key)}
              className="sr-only"
              aria-label={`${cfg.label} indicator`}
            />
            <span
              className={`w-2.5 h-2.5 rounded-sm border flex-shrink-0 flex items-center justify-center transition-colors ${
                cfg.enabled
                  ? "bg-[var(--accent-blue)] border-[var(--accent-blue)]"
                  : "border-[var(--text-muted)]"
              }`}
              aria-hidden="true"
            >
              {cfg.enabled && (
                <svg className="w-2 h-2 text-[var(--foreground)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </span>
            {cfg.label}
          </label>
        ))}
      </div>

      {/* Parameter controls */}
      {showParams && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px]">
          {configs.map((cfg) => (
            <div
              key={cfg.key}
              className={`bg-[var(--bg-secondary)] rounded-lg p-2 border border-[var(--border-subtle)] space-y-1 ${
                !cfg.enabled ? "opacity-40" : ""
              }`}
            >
              <span className="text-[var(--text-secondary)] font-medium uppercase tracking-wider">
                {cfg.label}
              </span>
              {Object.entries(cfg.params).map(([param, value]) => (
                <div key={param} className="flex items-center justify-between gap-1">
                  <span className="text-[var(--text-muted)]">{param}</span>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={value}
                    onChange={(e) => updateParam(cfg.key, param, Math.max(1, parseInt(e.target.value) || 1))}
                    disabled={!cfg.enabled}
                    className="w-12 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded px-1 py-0.5 text-right text-[var(--foreground)] mono-nums focus:outline-none focus:border-[var(--accent-blue)]"
                    aria-label={`${cfg.label} ${param}`}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Chart panels */}
      {indicators.rsi && (
        <ChartPanel title="RSI" legends={[{ color: "#22c55e", label: "RSI" }]}>
          <RSIChart data={indicators.rsi} width={800} />
        </ChartPanel>
      )}

      {indicators.macd && (
        <ChartPanel
          title="MACD"
          legends={[
            { color: "#3b82f6", label: "MACD" },
            { color: "#f97316", label: "Signal" },
          ]}
        >
          <MACDChart
            macd={indicators.macd.macd}
            signal={indicators.macd.signal}
            histogram={indicators.macd.histogram}
            width={800}
          />
        </ChartPanel>
      )}

      {indicators.kd && (
        <ChartPanel
          title="KD"
          legends={[
            { color: "#3b82f6", label: "K" },
            { color: "#f97316", label: "D" },
          ]}
        >
          <KDChart k={indicators.kd.k} d={indicators.kd.d} width={800} />
        </ChartPanel>
      )}

      {indicators.bias && (
        <ChartPanel title="BIAS" legends={[{ color: "#3b82f6", label: "BIAS" }]}>
          <BiasChart data={indicators.bias} width={800} />
        </ChartPanel>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart panel wrapper
// ---------------------------------------------------------------------------

function ChartPanel({
  title,
  legends,
  children,
}: {
  title: string;
  legends: { color: string; label: string }[];
  children: React.ReactNode;
}) {
  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--border-subtle)]">
        <span className="text-[10px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
          {title}
        </span>
        <div className="flex items-center gap-3">
          {legends.map((l) => (
            <span key={l.label} className="flex items-center gap-1 text-[9px] text-[var(--text-muted)]">
              <span className="inline-block w-2.5 h-[2px] rounded-full" style={{ backgroundColor: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
      </div>
      <div className="w-full overflow-x-auto">{children}</div>
    </div>
  );
}
