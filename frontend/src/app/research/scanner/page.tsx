"use client";

import { useState, useCallback } from "react";
import { useRunScan, type SignalAction, type ScanResult } from "@/hooks/use-scanner";
import { SignalTable } from "@/app/scanner/components/signal-table";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
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
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* LEFT: Strategy selection (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <GlassPanel title="SIGNAL ENGINE">
              <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                SELECT STRATEGIES
              </h4>

              {/* Strategy toggles */}
              <div className="grid grid-cols-1 gap-2 mb-6">
                {STRATEGY_OPTIONS.map((opt) => {
                  const isActive = selectedStrategies.includes(opt.key);
                  return (
                    <button
                      key={opt.key}
                      onClick={() => toggleStrategy(opt.key)}
                      className="group relative px-4 py-2 text-left transition-all duration-200"
                      style={{
                        background: isActive ? "var(--accent-primary)" : "var(--bg-secondary)",
                        border: "1px solid var(--border-subtle)",
                        clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))"
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-[11px] font-bold ${isActive ? "text-white" : "text-[var(--text-secondary)] group-hover:text-[var(--foreground)]"}`}>
                          {opt.label.toUpperCase()}
                        </span>
                        {isActive && <div className="w-1.5 h-1.5 bg-white rotate-45" />}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Scan button */}
              <div className="pt-4 border-t border-[var(--border-subtle)] space-y-3">
                <ClippedButton
                  variant="red-solid"
                  size="md"
                  onClick={handleScan}
                  disabled={runScan.isPending}
                  className="w-full"
                >
                  {runScan.isPending ? "INITIALIZING SCAN..." : "RUN FULL MARKET SCAN"}
                </ClippedButton>
                
                {scanResult && (
                  <div className="flex items-center justify-center gap-2 text-[10px] font-bold text-[var(--text-muted)]">
                    <span className="w-1.5 h-1.5 bg-[var(--stock-up)] animate-pulse" />
                    LAST SCAN: {formatTime(scanResult.scannedAt)}
                  </div>
                )}
              </div>

              {/* Summary counts */}
              {scanResult && (
                <div className="mt-6 space-y-1">
                  <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                    COMPOSITE SUMMARY
                  </h4>
                  {SUMMARY_ITEMS.map(({ action, label, color }) => (
                    <div
                      key={action}
                      className="flex items-center justify-between px-3 py-2 bg-[var(--bg-secondary)]/50 border-b border-[var(--border-subtle)]"
                    >
                      <span className="text-[10px] font-bold text-[var(--text-secondary)]">{label.toUpperCase()}</span>
                      <span className="text-sm font-bold tabular-nums" style={{ color }}>
                        {countByAction(stocks, action)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </GlassPanel>
          </div>

          {/* RIGHT: Results (8 cols) */}
          <div className="lg:col-span-8">
            <GlassPanel title={scanResult ? `SCAN RESULTS [${stocks.length}]` : "ENGINE STANDBY"} noPadding>
              <div className="min-h-[600px] flex flex-col">
                {runScan.isPending ? (
                  <div className="flex-1 flex items-center justify-center">
                    <LoadingSpinner />
                  </div>
                ) : runScan.isError ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                    <p className="text-red-400 font-bold text-sm mb-4 uppercase tracking-widest">
                      {runScan.error instanceof Error ? runScan.error.message : "SCAN FAILURE"}
                    </p>
                    <ClippedButton variant="red-ghost" size="sm" onClick={handleScan}>
                      RETRY SCAN
                    </ClippedButton>
                  </div>
                ) : !scanResult ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center opacity-30">
                    <div className="w-16 h-16 mb-4 border-2 border-dashed border-[var(--text-muted)] rounded-full flex items-center justify-center">
                      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em]">Ready for analysis</p>
                  </div>
                ) : (
                  <div className="p-4">
                    <div className="flex items-center justify-end mb-4">
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
                        className="text-[10px] font-bold px-3 py-1 bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] transition-colors"
                      >
                        EXPORT CSV
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
            </GlassPanel>
          </div>
        </div>
      </main>
    </div>
  );
}
