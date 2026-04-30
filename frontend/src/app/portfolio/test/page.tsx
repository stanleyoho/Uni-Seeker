"use client";

import { useState, useCallback } from "react";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
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
  /* ── Allocation state ── */
  const [allocations, setAllocations] = useState<PortfolioAllocation[]>([
    { symbol: "2330.TW", weight: 40, strategy: "sma_cross" },
    { symbol: "AAPL", weight: 30, strategy: "buy_and_hold" },
    { symbol: "0050.TW", weight: 30, strategy: "buy_and_hold" },
  ]);

  /* ── Rebalance state ── */
  const [rebalanceMode, setRebalanceMode] = useState<RebalanceMode>("periodic");
  const [periodDays, setPeriodDays] = useState(30);
  const [thresholdPct, setThresholdPct] = useState(5);
  const [initialCapital, setInitialCapital] = useState(1_000_000);

  /* ── Result state ── */
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

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      <h1
        style={{
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: "-0.04em",
          color: "#fff",
          marginBottom: 20,
        }}
      >
        組合回測
      </h1>

      <div className="flex flex-col lg:flex-row gap-4 mb-4">
        {/* ── Left Panel: Configuration ── */}
        <div className="lg:w-[380px] lg:shrink-0">
          <GlassPanel className="sticky top-20">
            <div className="space-y-4">
              {/* Allocation Editor */}
              <AllocationEditor
                allocations={allocations}
                onChange={setAllocations}
                strategies={MOCK_STRATEGIES}
              />

              {/* Divider */}
              <div
                style={{
                  borderTop: "1px solid var(--border-color)",
                }}
              />

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
                <p
                  style={{
                    fontSize: 10,
                    color: "#9CA3AF",
                    textAlign: "center",
                  }}
                >
                  {allocations.some((a) => !a.symbol.trim())
                    ? "請填入所有標的代號"
                    : `權重合計須為 100% (目前 ${totalWeight.toFixed(0)}%)`}
                </p>
              )}

              {/* Error display */}
              {backtest.isError && (
                <div
                  style={{
                    padding: "8px 12px",
                    background: "rgba(238,63,44,0.1)",
                    border: "1px solid rgba(238,63,44,0.2)",
                  }}
                >
                  <p style={{ color: "#EE3F2C", fontSize: 12 }}>
                    {backtest.error instanceof Error
                      ? backtest.error.message
                      : "回測失敗"}
                  </p>
                </div>
              )}
            </div>
          </GlassPanel>
        </div>

        {/* ── Right Panel: Results ── */}
        <div className="flex-1 min-w-0">
          {!result && !backtest.isPending && (
            <GlassPanel className="flex items-center justify-center min-h-[400px]">
              <div className="text-center">
                <div
                  style={{
                    width: 64,
                    height: 64,
                    margin: "0 auto 16px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.10)",
                  }}
                >
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <path
                      d="M4 20L10 14L14 18L20 10L24 14"
                      stroke="#EE3F2C"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeOpacity="0.6"
                    />
                    <path
                      d="M4 24L10 17L14 21L20 13L24 17"
                      stroke="#00E5FF"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeOpacity="0.3"
                    />
                  </svg>
                </div>
                <p style={{ color: "#9CA3AF", fontSize: 14, marginBottom: 4 }}>
                  尚無回測結果
                </p>
                <p style={{ color: "#9CA3AF", fontSize: 12, opacity: 0.6 }}>
                  配置標的與權重後，點擊「執行組合回測」
                </p>
              </div>
            </GlassPanel>
          )}

          {result && (
            <GlassPanel noPadding>
              <div style={{ padding: 24 }}>
                <PortfolioComparison
                  result={result}
                  initialCapital={initialCapital}
                />
              </div>
            </GlassPanel>
          )}
        </div>
      </div>
    </div>
  );
}
