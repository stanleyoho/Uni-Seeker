"use client";

import { useState, useCallback } from "react";
import { useRunScan, type SignalAction, type ScanResult } from "@/hooks/use-scanner";
import { SignalTable } from "./components/signal-table";
import { StatCard } from "@/components/ui/stat-card";
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
    <div className="p-3 md:p-4 max-w-[1440px] mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-[var(--foreground)] tracking-tight">
            訊號掃描
          </h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">
            掃描全市場股票的技術指標訊號
          </p>
        </div>
      </div>

      {/* Control bar */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl p-4 mb-4">
        <div className="flex flex-col gap-3">
          {/* Strategy filter */}
          <div>
            <span className="text-xs text-[var(--text-muted)] mb-2 block">
              策略選擇（不勾選則使用全部）
            </span>
            <div className="flex flex-wrap gap-2">
              {STRATEGY_OPTIONS.map((opt) => {
                const isActive = selectedStrategies.includes(opt.key);
                return (
                  <label
                    key={opt.key}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition-all duration-150 select-none ${
                      isActive
                        ? "bg-[var(--accent-blue)]/15 border-[var(--accent-blue)]/30 text-[var(--accent-blue)]"
                        : "bg-[var(--card-bg)] border-[var(--border-color)] text-[var(--text-secondary)] hover:border-[var(--accent-blue)]/20 hover:text-[var(--foreground)]"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={() => toggleStrategy(opt.key)}
                      className="sr-only"
                      aria-label={`Select ${opt.label} strategy`}
                    />
                    <span
                      className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
                        isActive
                          ? "bg-[var(--accent-blue)] border-[var(--accent-blue)]"
                          : "border-[var(--border-color)]"
                      }`}
                    >
                      {isActive && (
                        <svg className="w-2.5 h-2.5 text-[var(--foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </span>
                    {opt.label}
                  </label>
                );
              })}
            </div>
          </div>

          {/* Scan button and last scan time */}
          <div className="flex items-center gap-4 pt-2 border-t border-[var(--border-subtle)]">
            <button
              onClick={handleScan}
              disabled={runScan.isPending}
              className="px-5 py-2 text-sm font-medium rounded-xl bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] text-white transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-blue-600/20"
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
            </button>
            {scanResult && (
              <span className="text-[10px] text-[var(--text-muted)] flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                最後掃描: {formatTime(scanResult.scannedAt)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Summary cards */}
      {scanResult && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-4">
          <StatCard
            label="強力買進"
            value={countByAction(stocks, "STRONG_BUY")}
            size="sm"
            className="border-l-2 border-l-emerald-500"
          />
          <StatCard
            label="買進"
            value={countByAction(stocks, "BUY")}
            size="sm"
            className="border-l-2 border-l-green-500"
          />
          <StatCard
            label="持有"
            value={countByAction(stocks, "HOLD")}
            size="sm"
            className="border-l-2 border-l-slate-500"
          />
          <StatCard
            label="賣出"
            value={countByAction(stocks, "SELL")}
            size="sm"
            className="border-l-2 border-l-red-400"
          />
          <StatCard
            label="強力賣出"
            value={countByAction(stocks, "STRONG_SELL")}
            size="sm"
            className="border-l-2 border-l-red-600"
          />
        </div>
      )}

      {/* Loading state */}
      {runScan.isPending && <LoadingSpinner text="掃描全市場訊號中..." size="sm" />}

      {/* Error */}
      {runScan.isError && (
        <div className="bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-xl p-6 text-center mb-4">
          <p className="text-red-400 mb-3">
            {runScan.error instanceof Error ? runScan.error.message : "掃描失敗"}
          </p>
          <button
            onClick={handleScan}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-[var(--card-bg)] border border-[var(--border-color)] text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-all duration-200"
          >
            重試
          </button>
        </div>
      )}

      {/* Empty state before first scan */}
      {!scanResult && !runScan.isPending && (
        <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl p-12 text-center">
          <div className="text-[var(--text-muted)] mb-3 flex justify-center">
            <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 className="text-[var(--foreground)] font-semibold mb-1">尚未執行掃描</h3>
          <p className="text-[var(--text-muted)] text-sm">
            選擇策略後點擊「開始掃描」，分析全市場技術指標訊號
          </p>
        </div>
      )}

      {/* Signal table */}
      {scanResult && !runScan.isPending && stocks.length > 0 && (
        <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-[var(--foreground)]">
              掃描結果
              <span className="text-[var(--text-muted)] font-normal ml-2 text-xs">
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
              className="text-[10px] px-2 py-1 rounded border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--foreground)] hover:border-[var(--accent-blue)] transition-colors"
            >
              ↓ 匯出 CSV
            </button>
          </div>
          <SignalTable
            stocks={stocks}
            actionFilter={actionFilter}
            onActionFilterChange={setActionFilter}
          />
        </div>
      )}
    </div>
  );
}
