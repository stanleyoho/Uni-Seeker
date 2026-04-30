"use client";

import { useState, useCallback } from "react";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { StrategyBuilder, type BacktestConfig } from "@/app/backtest/components/strategy-builder";
import { BacktestQueue, type QueueJob } from "@/app/backtest/components/backtest-queue";
import { BacktestResults } from "@/app/backtest/components/backtest-results";
import { BacktestHistory } from "@/app/backtest/components/backtest-history";
import { useRunBacktest } from "@/hooks/use-backtest";
import { type BacktestResult } from "@/lib/api-client";

/* ---------- Internal Tabs ---------- */

const TABS = [
  { key: "builder", label: "策略建構" },
  { key: "queue", label: "回測佇列" },
  { key: "results", label: "回測結果" },
  { key: "history", label: "歷史紀錄" },
] as const;

/* ---------- Page ---------- */

export default function BacktestPage() {
  const [activeTab, setActiveTab] = useState("builder");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [queueJobs, setQueueJobs] = useState<QueueJob[]>([]);
  const [error, setError] = useState<string | null>(null);

  const runMutation = useRunBacktest();

  const handleRunNow = useCallback(
    async (config: BacktestConfig) => {
      setError(null);
      setResult(null);
      setActiveTab("results");

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
        setActiveTab("builder");
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
      setActiveTab("queue");
    },
    []
  );

  const handleCancelJob = useCallback((id: string) => {
    setQueueJobs((prev) => prev.filter((j) => j.id !== id));
  }, []);

  const handleViewResult = useCallback(
    (_id: string) => {
      // Wave 2: fetch result by job id
      setActiveTab("results");
    },
    []
  );

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Header + STRATOS-styled tab buttons */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-6">
        <h1
          className="text-xl md:text-2xl font-bold tracking-tight"
          style={{ color: "var(--foreground)" }}
        >
          策略回測
        </h1>

        <div className="flex gap-2 flex-wrap">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.key;
            return (
              <ClippedButton
                key={tab.key}
                variant={isActive ? "cyan-ghost" : "red-ghost"}
                size="sm"
                onClick={() => setActiveTab(tab.key)}
                className={isActive ? "opacity-100" : "opacity-60 hover:opacity-90"}
              >
                {tab.label}
              </ClippedButton>
            );
          })}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <GlassPanel className="mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </GlassPanel>
      )}

      {/* Loading overlay for run mutation */}
      {runMutation.isPending && activeTab === "results" && (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-[var(--accent-cyan)]/30 border-t-[var(--accent-cyan)] rounded-full animate-spin" />
            <span style={{ color: "var(--text-muted)", fontSize: 14 }}>
              回測執行中...
            </span>
          </div>
        </div>
      )}

      {/* Tab content */}
      <div className={runMutation.isPending && activeTab === "results" ? "hidden" : ""}>
        {activeTab === "builder" && (
          <GlassPanel title="策略建構" className="max-w-2xl">
            <StrategyBuilder onEnqueue={handleEnqueue} onRunNow={handleRunNow} />
          </GlassPanel>
        )}

        {activeTab === "queue" && (
          <GlassPanel title="回測佇列">
            <BacktestQueue
              jobs={queueJobs.length > 0 ? queueJobs : undefined}
              onCancel={handleCancelJob}
              onViewResult={handleViewResult}
            />
          </GlassPanel>
        )}

        {activeTab === "results" && (
          <GlassPanel title="回測結果">
            <BacktestResults result={result} />
          </GlassPanel>
        )}

        {activeTab === "history" && (
          <GlassPanel title="歷史紀錄">
            <BacktestHistory />
          </GlassPanel>
        )}
      </div>
    </div>
  );
}
