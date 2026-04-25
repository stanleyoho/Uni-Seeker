"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";
import type { StockPrice } from "@/lib/api-client";

interface StockChartProps {
  prices: StockPrice[];
  height?: number;
  showVolume?: boolean;
}

// Simple Moving Average calculation
function calcSMA(prices: { date: string; close: number }[], period: number): { time: Time; value: number }[] {
  const result: { time: Time; value: number }[] = [];
  for (let i = period - 1; i < prices.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += prices[i - j].close;
    }
    result.push({ time: prices[i].date as Time, value: sum / period });
  }
  return result;
}

const MA_OPTIONS = [
  { period: 5, color: "#f59e0b", label: "MA5" },
  { period: 10, color: "#8b5cf6", label: "MA10" },
  { period: 20, color: "#3b82f6", label: "MA20" },
  { period: 60, color: "#ef4444", label: "MA60" },
];

export function StockChart({ prices, height = 400, showVolume = true }: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [enabledMAs, setEnabledMAs] = useState<Set<number>>(new Set([5, 20]));

  const toggleMA = (period: number) => {
    setEnabledMAs((prev) => {
      const next = new Set(prev);
      if (next.has(period)) next.delete(period);
      else next.add(period);
      return next;
    });
  };

  useEffect(() => {
    if (!containerRef.current || prices.length === 0) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "#1a2332" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: {
        vertLine: { color: "#3b82f6", width: 1, labelBackgroundColor: "#3b82f6" },
        horzLine: { color: "#3b82f6", width: 1, labelBackgroundColor: "#3b82f6" },
      },
      rightPriceScale: { borderColor: "#1e293b" },
      timeScale: { borderColor: "#1e293b" },
    });

    const sorted = [...prices].sort((a, b) => a.date.localeCompare(b.date));
    const parsed = sorted.map((p) => ({
      date: p.date,
      open: parseFloat(p.open),
      high: parseFloat(p.high),
      low: parseFloat(p.low),
      close: parseFloat(p.close),
      volume: p.volume,
      change: parseFloat(p.change),
    }));

    // Candlestick
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderVisible: false,
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });
    candlestickSeries.setData(
      parsed.map((p) => ({
        time: p.date as Time,
        open: p.open,
        high: p.high,
        low: p.low,
        close: p.close,
      })) as CandlestickData<Time>[],
    );

    // MA overlays
    for (const ma of MA_OPTIONS) {
      if (!enabledMAs.has(ma.period)) continue;
      if (parsed.length < ma.period) continue;

      const maData = calcSMA(parsed, ma.period);
      const lineSeries = chart.addSeries(LineSeries, {
        color: ma.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      lineSeries.setData(maData as LineData<Time>[]);
    }

    // Volume histogram
    if (showVolume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volumeSeries.setData(
        parsed.map((p) => ({
          time: p.date as Time,
          value: p.volume,
          color: p.change >= 0 ? "rgba(239, 68, 68, 0.3)" : "rgba(34, 197, 94, 0.3)",
        })) as HistogramData<Time>[],
      );
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [prices, height, showVolume, enabledMAs]);

  return (
    <div>
      {/* MA toggle buttons */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-[var(--text-muted)]">MA:</span>
        {MA_OPTIONS.map((ma) => (
          <button
            key={ma.period}
            onClick={() => toggleMA(ma.period)}
            className={`text-xs px-2 py-1 rounded-md border transition-all duration-200 font-mono ${
              enabledMAs.has(ma.period)
                ? "border-current opacity-100"
                : "border-[var(--border-color)] opacity-40 hover:opacity-70"
            }`}
            style={{ color: ma.color }}
          >
            {ma.label}
          </button>
        ))}
      </div>
      <div ref={containerRef} className="w-full rounded-xl overflow-hidden" />
    </div>
  );
}
