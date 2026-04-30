"use client";

import { useState, useCallback } from "react";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { StrategyBuilder, type BacktestConfig } from "@/app/backtest/components/strategy-builder";
import { BacktestQueue, type QueueJob } from "@/app/backtest/components/backtest-queue";
import { BacktestResults } from "@/app/backtest/components/backtest-results";
import { BacktestHistory } from "@/app/backtest/components/backtest-history";
import { useRunBacktest } from "@/hooks/use-backtest";
import { type BacktestResult } from "@/lib/api-client";

export default function BacktestPage() {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [queueJobs, setQueueJobs] = useState<QueueJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [rightPanel, setRightPanel] = useState<"results" | "queue" | "history">("results");

  const runMutation = useRunBacktest();

  const handleRunNow = useCallback(
    async (config: BacktestConfig) => {
      setError(null);
      setResult(null);
      setRightPanel("results");

      try {
        const res = await runMutation.mutateAsync({
          symbol: config.symbol,
          strategy: config.strategies[0],
          params: Object.keys(config.params).length > 0 ? config.params : undefined,
          initial_capital: config.initialCapital,
          position_size: config.positionSize,
        });
        setResult(res);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
      }
    },
    [runMutation]
  );

  const handleEnqueue = useCallback(
    (config: BacktestConfig) => {
      const newJob: QueueJob = {
        id: `q-${Date.now()}`,
        symbol: config.symbol,
        strategy: config.strategies.join(" + "),
        status: "pending",
        progress: 0,
        createdAt: new Date().toLocaleString("zh-TW", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setQueueJobs((prev) => [...prev, newJob]);
      setRightPanel("queue");
    },
    []
  );

  const handleCancelJob = useCallback((id: string) => {
    setQueueJobs((prev) => prev.filter((j) => j.id !== id));
  }, []);

  const handleViewResult = useCallback(
    (_id: string) => {
      setRightPanel("results");
    },
    []
  );

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Left Panel: Strategy Config (4col equivalent) */}
        <div className="lg:w-[380px] lg:shrink-0">
          <GlassPanel className="sticky top-20">
            <div className="space-y-4">
              {/* Panel title */}
              <div className="flex items-center gap-2 pb-3" style={{ borderBottom: "1px solid var(--border-color)" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 20V10" /><path d="M18 20V4" /><path d="M6 20v-4" />
                </svg>
                <span className="text-[13px] font-bold uppercase tracking-tight text-[var(--text-muted)]">
                  策略設定
                </span>
              </div>

              <StrategyBuilder onEnqueue={handleEnqueue} onRunNow={handleRunNow} />

              {/* Error display */}
              {error && (
                <div
                  className="px-3 py-2"
                  style={{
                    background: "rgba(238,63,44,0.1)",
                    border: "1px solid rgba(238,63,44,0.2)",
                  }}
                >
                  <p className="text-[#EE3F2C] text-xs">{error}</p>
                </div>
              )}
            </div>
          </GlassPanel>
        </div>

        {/* Right Panel: Results (8col equivalent) */}
        <div className="flex-1 min-w-0">
          {/* Right panel sub-navigation */}
          <div className="flex items-center gap-2 mb-3">
            {(
              [
                { key: "results", label: "回測結果" },
                { key: "queue", label: `佇列 (${queueJobs.length})` },
                { key: "history", label: "歷史紀錄" },
              ] as const
            ).map((tab) => (
              <ClippedButton
                key={tab.key}
                variant={rightPanel === tab.key ? "cyan-ghost" : "red-ghost"}
                size="sm"
                onClick={() => setRightPanel(tab.key)}
                className={rightPanel === tab.key ? "opacity-100" : "opacity-50 hover:opacity-80"}
              >
                {tab.label}
              </ClippedButton>
            ))}
          </div>

          {/* Results */}
          {rightPanel === "results" && (
            <>
              {runMutation.isPending ? (
                <GlassPanel className="flex items-center justify-center min-h-[400px]">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border-2 border-[var(--accent-cyan)]/30 border-t-[var(--accent-cyan)] rounded-full animate-spin" />
                    <span className="text-[var(--text-muted)] text-sm">回測執行中...</span>
                  </div>
                </GlassPanel>
              ) : result ? (
                <GlassPanel noPadding>
                  <div style={{ padding: 24 }}>
                    <BacktestResults result={result} />
                  </div>
                </GlassPanel>
              ) : (
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
                    <p className="text-[var(--text-muted)] text-sm mb-1">請先執行回測</p>
                    <p className="text-[var(--text-muted)] text-xs opacity-60">
                      在左側設定策略參數後，點擊「立即執行」或「加入佇列」
                    </p>
                  </div>
                </GlassPanel>
              )}
            </>
          )}

          {/* Queue */}
          {rightPanel === "queue" && (
            <GlassPanel>
              <BacktestQueue
                jobs={queueJobs.length > 0 ? queueJobs : undefined}
                onCancel={handleCancelJob}
                onViewResult={handleViewResult}
              />
            </GlassPanel>
          )}

          {/* History */}
          {rightPanel === "history" && (
            <GlassPanel>
              <BacktestHistory />
            </GlassPanel>
          )}
        </div>
      </div>
    </div>
  );
}
