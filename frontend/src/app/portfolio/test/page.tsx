"use client";

import { useState, useCallback } from "react";
import { GlassPanel, ClippedButton, KpiCard } from "@/components/stratos/primitives";
import { AllocationEditor } from "@/app/portfolio/components/allocation-editor";
import { RebalanceConfig } from "@/app/portfolio/components/rebalance-config";
import { PortfolioComparison } from "@/app/portfolio/components/portfolio-comparison";
import {
  usePortfolioBacktest,
  type PortfolioAllocation,
  type RebalanceMode,
  type PortfolioBacktestResult,
} from "@/hooks/use-portfolio";

const MOCK_STRATEGIES = [
  "sma_cross",
  "rsi_reversal",
  "macd_signal",
  "bollinger_breakout",
  "buy_and_hold",
];

export default function PortfolioTestPage() {
  /* -- Allocation state -- */
  const [allocations, setAllocations] = useState<PortfolioAllocation[]>([
    { symbol: "2330.TW", weight: 40, strategy: "sma_cross" },
    { symbol: "AAPL", weight: 30, strategy: "buy_and_hold" },
    { symbol: "0050.TW", weight: 30, strategy: "buy_and_hold" },
  ]);

  /* -- Rebalance state -- */
  const [rebalanceMode, setRebalanceMode] = useState<RebalanceMode>("periodic");
  const [periodDays, setPeriodDays] = useState(30);
  const [thresholdPct, setThresholdPct] = useState(5);
  const [initialCapital, setInitialCapital] = useState(1_000_000);

  /* -- Result state -- */
  const [result, setResult] = useState<PortfolioBacktestResult | null>(null);
  const backtest = usePortfolioBacktest();

  const totalWeight = allocations.reduce((sum, a) => sum + a.weight, 0);
  const isValid =
    allocations.length > 0 &&
    allocations.every((a) => a.symbol.trim() !== "") &&
    Math.abs(totalWeight - 100) < 0.01;

  const handleRun = useCallback(async () => {
    if (!isValid) return;
    const res = await backtest.mutateAsync({
      allocations,
      rebalance_mode: rebalanceMode,
      rebalance_period_days: periodDays,
      rebalance_threshold_pct: thresholdPct,
      initial_capital: initialCapital,
    });
    setResult(res);
  }, [
    allocations,
    rebalanceMode,
    periodDays,
    thresholdPct,
    initialCapital,
    isValid,
    backtest,
  ]);

  /* -- Derive KPI directions -- */
  const retDir = result
    ? result.total_return >= 0 ? "up" : "down"
    : "flat";
  const sharpeDir = result
    ? result.sharpe_ratio >= 1 ? "up" : result.sharpe_ratio >= 0 ? "flat" : "down"
    : "flat";
  const ddDir = result
    ? result.max_drawdown > -0.1 ? "up" : result.max_drawdown > -0.2 ? "flat" : "down"
    : "flat";

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left Panel: Configuration */}
        <div className="lg:w-[380px] lg:shrink-0">
          <GlassPanel className="sticky top-[104px]">
            <div className="space-y-4">
              {/* Panel title */}
              <div className="flex items-center gap-2 pb-3" style={{ borderBottom: "1px solid var(--border-color)" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
                </svg>
                <span className="text-[13px] font-bold uppercase tracking-tight text-[var(--text-muted)]">
                  組合配置
                </span>
              </div>

              {/* Allocation Editor */}
              <AllocationEditor
                allocations={allocations}
                onChange={setAllocations}
                strategies={MOCK_STRATEGIES}
              />

              {/* Divider */}
              <div style={{ borderTop: "1px solid var(--border-color)" }} />

              {/* Rebalance Config */}
              <RebalanceConfig
                mode={rebalanceMode}
                onModeChange={setRebalanceMode}
                periodDays={periodDays}
                onPeriodDaysChange={setPeriodDays}
                thresholdPct={thresholdPct}
                onThresholdPctChange={setThresholdPct}
                initialCapital={initialCapital}
                onInitialCapitalChange={setInitialCapital}
              />

              {/* Run button */}
              <ClippedButton
                variant="red-solid"
                size="lg"
                onClick={handleRun}
                disabled={backtest.isPending || !isValid}
                className="w-full"
              >
                {backtest.isPending ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    回測中...
                  </span>
                ) : (
                  "執行組合回測"
                )}
              </ClippedButton>

              {/* Validation hint */}
              {!isValid && allocations.length > 0 && (
                <p className="text-[10px] text-[var(--text-muted)] text-center">
                  {allocations.some((a) => !a.symbol.trim())
                    ? "請填入所有標的代號"
                    : `權重合計須為 100% (目前 ${totalWeight.toFixed(0)}%)`}
                </p>
              )}
            </div>
          </GlassPanel>
        </div>

        {/* Right Panel: Results */}
        <div className="flex-1 min-w-0">
          {/* Error banner */}
          {backtest.isError && (
            <div
              className="px-4 py-3 mb-3 flex items-center gap-2"
              style={{
                background: "rgba(238,63,44,0.08)",
                border: "1px solid rgba(238,63,44,0.25)",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#EE3F2C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              <p className="text-[#EE3F2C] text-xs flex-1">
                {backtest.error instanceof Error ? backtest.error.message : "回測失敗"}
              </p>
            </div>
          )}

          {/* Loading */}
          {backtest.isPending && (
            <GlassPanel className="flex items-center justify-center min-h-[400px]">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-[var(--accent-cyan)]/30 border-t-[var(--accent-cyan)] rounded-full animate-spin" />
                <span className="text-[var(--text-muted)] text-sm">組合回測執行中...</span>
              </div>
            </GlassPanel>
          )}

          {/* Empty state */}
          {!result && !backtest.isPending && (
            <GlassPanel className="flex items-center justify-center min-h-[400px]">
              <div className="text-center">
                <div
                  className="w-16 h-16 mx-auto mb-4 flex items-center justify-center"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.10)",
                  }}
                >
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <path d="M4 20L10 14L14 18L20 10L24 14" stroke="#EE3F2C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.6" />
                    <path d="M4 24L10 17L14 21L20 13L24 17" stroke="#00E5FF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" strokeOpacity="0.3" />
                  </svg>
                </div>
                <p className="text-[var(--text-muted)] text-sm mb-1">Portfolio Lab</p>
                <p className="text-[var(--text-muted)] text-xs opacity-60 max-w-xs mx-auto leading-relaxed">
                  配置標的、權重與策略後，點擊「執行組合回測」查看組合績效與個股比較
                </p>
              </div>
            </GlassPanel>
          )}

          {/* Results with KPI cards */}
          {result && !backtest.isPending && (
            <div className="space-y-4">
              {/* KPI Metrics Row */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <KpiCard
                  label="Total Return"
                  value={`${(result.total_return * 100).toFixed(1)}%`}
                  delta={`${allocations.length} assets`}
                  direction={retDir as "up" | "down" | "flat"}
                />
                <KpiCard
                  label="Sharpe Ratio"
                  value={result.sharpe_ratio.toFixed(2)}
                  delta={`ann. ${(result.annualized_return * 100).toFixed(1)}%`}
                  direction={sharpeDir as "up" | "down" | "flat"}
                />
                <KpiCard
                  label="Max Drawdown"
                  value={`${(result.max_drawdown * 100).toFixed(1)}%`}
                  delta="portfolio"
                  direction={ddDir as "up" | "down" | "flat"}
                />
                <KpiCard
                  label="Rebalance Events"
                  value={`${result.rebalance_log.length}`}
                  delta={rebalanceMode === "none" ? "disabled" : rebalanceMode === "periodic" ? `every ${periodDays}d` : `${thresholdPct}% threshold`}
                  direction="flat"
                />
              </div>

              {/* Equity Curves + Stock Metrics + Rebalance Log */}
              <GlassPanel noPadding>
                <div style={{ padding: 24 }}>
                  <PortfolioComparison
                    result={result}
                    initialCapital={initialCapital}
                  />
                </div>
              </GlassPanel>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
