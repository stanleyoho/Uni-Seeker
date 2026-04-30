"use client";

import { useState, useCallback } from "react";
import { useRunScan, type SignalAction, type ScanResult } from "@/hooks/use-scanner";
import { SignalTable } from "@/app/scanner/components/signal-table";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { downloadCSV } from "@/lib/csv-export";

const STRATEGY_OPTIONS = [
  { key: "RSI", label: "RSI" },
  { key: "MACD", label: "MACD" },
  { key: "BB", label: "Bollinger Bands" },
  { key: "KD", label: "KD" },
  { key: "SMA_CROSS", label: "SMA Cross" },
  { key: "VOLUME", label: "Volume" },
];

const ALL_ACTIONS: SignalAction[] = ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"];

const SUMMARY_ITEMS: { action: SignalAction; label: string; color: string }[] = [
  { action: "STRONG_BUY", label: "強力買進", color: "var(--stock-down)" },
  { action: "BUY", label: "買進", color: "#22c55e" },
  { action: "HOLD", label: "持有", color: "#64748b" },
  { action: "SELL", label: "賣出", color: "#f87171" },
  { action: "STRONG_SELL", label: "強力賣出", color: "var(--stock-up)" },
];

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function countByAction(stocks: ScanResult["stocks"], action: SignalAction): number {
  return stocks.filter((s) => s.compositeAction === action).length;
}

export default function ScannerPage() {
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [actionFilter, setActionFilter] = useState<SignalAction[]>([...ALL_ACTIONS]);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  const runScan = useRunScan();

  const handleScan = useCallback(() => {
    const keys = selectedStrategies.length > 0 ? selectedStrategies : undefined;
    runScan.mutate(keys, {
      onSuccess: (data) => setScanResult(data),
    });
  }, [selectedStrategies, runScan]);

  const toggleStrategy = (key: string) => {
    setSelectedStrategies((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const stocks = scanResult?.stocks ?? [];

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
        <div>
          <h1
            className="text-xl md:text-2xl font-bold tracking-tight"
            style={{ color: "var(--foreground)" }}
          >
            訊號掃描
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            掃描全市場股票的技術指標訊號
          </p>
        </div>
      </div>

      {/* Strategy selection */}
      <GlassPanel className="mb-4">
        <div className="flex flex-col gap-3">
          {/* Strategy filter pills */}
          <div>
            <span
              className="text-xs mb-2 block"
              style={{ color: "var(--text-muted)" }}
            >
              策略選擇（不勾選則使用全部）
            </span>
            <div className="flex flex-wrap gap-2">
              {STRATEGY_OPTIONS.map((opt) => {
                const isActive = selectedStrategies.includes(opt.key);
                return (
                  <button
                    key={opt.key}
                    onClick={() => toggleStrategy(opt.key)}
                    className="text-xs px-4 py-1.5 font-medium transition-all duration-150 select-none"
                    style={{
                      borderRadius: 9999,
                      border: isActive
                        ? "1px solid var(--accent-primary)"
                        : "1px solid var(--border-color)",
                      background: isActive
                        ? "rgba(238, 63, 44, 0.12)"
                        : "transparent",
                      color: isActive
                        ? "var(--accent-primary)"
                        : "var(--foreground)",
                    }}
                    aria-pressed={isActive}
                    aria-label={`Select ${opt.label} strategy`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Scan button and last scan time */}
          <div
            className="flex items-center gap-4 pt-3"
            style={{ borderTop: "1px solid var(--border-color)" }}
          >
            <ClippedButton
              variant="red-solid"
              size="md"
              onClick={handleScan}
              disabled={runScan.isPending}
            >
              {runScan.isPending ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  掃描中...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  開始掃描
                </span>
              )}
            </ClippedButton>
            {scanResult && (
              <span
                className="text-[10px] flex items-center gap-1.5"
                style={{ color: "var(--text-muted)" }}
              >
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
                  style={{ background: "var(--stock-down)" }}
                />
                最後掃描: {formatTime(scanResult.scannedAt)}
              </span>
            )}
          </div>
        </div>
      </GlassPanel>

      {/* Summary cards */}
      {scanResult && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-4">
          {SUMMARY_ITEMS.map(({ action, label, color }) => (
            <GlassPanel key={action} className="!p-4">
              <div
                className="text-[10px] font-bold uppercase tracking-wider mb-1"
                style={{ color: "var(--text-muted)" }}
              >
                {label}
              </div>
              <div
                className="text-2xl font-semibold tabular-nums"
                style={{ color }}
              >
                {countByAction(stocks, action)}
              </div>
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Loading state */}
      {runScan.isPending && <LoadingSpinner text="掃描全市場訊號中..." size="sm" />}

      {/* Error */}
      {runScan.isError && (
        <GlassPanel className="mb-4">
          <div className="text-center py-4">
            <p className="mb-3" style={{ color: "var(--stock-up)" }}>
              {runScan.error instanceof Error ? runScan.error.message : "掃描失敗"}
            </p>
            <ClippedButton variant="red-ghost" size="sm" onClick={handleScan}>
              重試
            </ClippedButton>
          </div>
        </GlassPanel>
      )}

      {/* Empty state before first scan */}
      {!scanResult && !runScan.isPending && (
        <GlassPanel>
          <div className="text-center py-8">
            <div className="mb-3 flex justify-center" style={{ color: "var(--text-muted)" }}>
              <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="font-semibold mb-1" style={{ color: "var(--foreground)" }}>
              尚未執行掃描
            </h3>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              選擇策略後點擊「開始掃描」，分析全市場技術指標訊號
            </p>
          </div>
        </GlassPanel>
      )}

      {/* Signal table */}
      {scanResult && !runScan.isPending && stocks.length > 0 && (
        <GlassPanel>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              掃描結果
              <span className="font-normal ml-2 text-xs" style={{ color: "var(--text-muted)" }}>
                共 {stocks.length} 檔
              </span>
            </h2>
            <button
              onClick={() => {
                const csvData = stocks.map((s) => ({
                  股票代號: s.symbol,
                  股票名稱: s.name,
                  綜合訊號: s.compositeAction,
                  分數: s.score,
                  ...Object.fromEntries(
                    s.signals.map((sig) => [`${sig.strategy}_訊號`, sig.action])
                  ),
                }));
                downloadCSV(csvData, `scanner_${new Date().toISOString().slice(0, 10)}.csv`);
              }}
              className="text-[10px] px-2 py-1 transition-colors"
              style={{
                border: "1px solid var(--border-color)",
                color: "var(--text-muted)",
                borderRadius: 4,
              }}
            >
              ↓ 匯出 CSV
            </button>
          </div>
          <SignalTable
            stocks={stocks}
            actionFilter={actionFilter}
            onActionFilterChange={setActionFilter}
          />
        </GlassPanel>
      )}
    </div>
  );
}
