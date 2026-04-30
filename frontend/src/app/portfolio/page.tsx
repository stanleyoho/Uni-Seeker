"use client";

import { useState, useCallback } from "react";
import { AllocationEditor } from "./components/allocation-editor";
import { RebalanceConfig } from "./components/rebalance-config";
import { PortfolioComparison } from "./components/portfolio-comparison";
import {
  usePortfolioBacktest,
  type PortfolioAllocation,
  type RebalanceMode,
  type PortfolioBacktestResult,
} from "@/hooks/use-portfolio";

const MOCK_STRATEGIES = ["sma_cross", "rsi_reversal", "macd_signal", "bollinger_breakout", "buy_and_hold"];

export default function PortfolioPage() {
  // Allocation state
  const [allocations, setAllocations] = useState<PortfolioAllocation[]>([
    { symbol: "2330.TW", weight: 40, strategy: "sma_cross" },
    { symbol: "AAPL", weight: 30, strategy: "buy_and_hold" },
    { symbol: "0050.TW", weight: 30, strategy: "buy_and_hold" },
  ]);

  // Rebalance state
  const [rebalanceMode, setRebalanceMode] = useState<RebalanceMode>("periodic");
  const [periodDays, setPeriodDays] = useState(30);
  const [thresholdPct, setThresholdPct] = useState(5);
  const [initialCapital, setInitialCapital] = useState(1_000_000);

  // Result state
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
  }, [allocations, rebalanceMode, periodDays, thresholdPct, initialCapital, isValid, backtest]);

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      <h1 className="text-xl md:text-2xl font-bold mb-4 text-white tracking-tight">
        組合回測
      </h1>

      <div className="flex flex-col lg:flex-row gap-4 mb-4">
        {/* ── Left Panel: Configuration ── */}
        <div className="lg:w-[380px] lg:shrink-0">
          <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 sticky top-20 space-y-4">
            {/* Allocation Editor */}
            <AllocationEditor
              allocations={allocations}
              onChange={setAllocations}
              strategies={MOCK_STRATEGIES}
            />

            {/* Divider */}
            <div className="border-t border-[var(--border-subtle)]" />

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
            <button
              onClick={handleRun}
              disabled={backtest.isPending || !isValid}
              className="w-full py-2.5 bg-[var(--accent-blue)] text-white text-sm rounded-lg hover:bg-[var(--accent-blue-hover)] transition-all duration-200 disabled:opacity-50 font-medium"
            >
              {backtest.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  回測中...
                </span>
              ) : (
                "執行組合回測"
              )}
            </button>

            {/* Validation hint */}
            {!isValid && allocations.length > 0 && (
              <p className="text-[10px] text-[var(--text-muted)] text-center">
                {allocations.some((a) => !a.symbol.trim())
                  ? "請填入所有標的代號"
                  : `權重合計須為 100% (目前 ${totalWeight.toFixed(0)}%)`}
              </p>
            )}

            {/* Error display */}
            {backtest.isError && (
              <div className="px-3 py-2 bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-lg">
                <p className="text-red-400 text-xs">
                  {backtest.error instanceof Error ? backtest.error.message : "回測失敗"}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── Right Panel: Results ── */}
        <div className="flex-1 min-w-0">
          {!result && !backtest.isPending && (
            <div className="flex items-center justify-center h-full min-h-[400px]">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[var(--bg-secondary)] border border-[var(--border-subtle)] flex items-center justify-center">
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <path
                      d="M4 20L10 14L14 18L20 10L24 14"
                      stroke="#3b82f6"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeOpacity="0.4"
                    />
                    <path
                      d="M4 24L10 17L14 21L20 13L24 17"
                      stroke="#8b5cf6"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeOpacity="0.25"
                    />
                  </svg>
                </div>
                <p className="text-[var(--text-muted)] text-sm mb-1">尚無回測結果</p>
                <p className="text-[var(--text-muted)] text-xs opacity-60">
                  配置標的與權重後，點擊「執行組合回測」
                </p>
              </div>
            </div>
          )}

          {result && (
            <PortfolioComparison result={result} initialCapital={initialCapital} />
          )}
        </div>
      </div>
    </div>
  );
}
