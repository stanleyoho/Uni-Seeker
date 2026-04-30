"use client";

import { useState, useCallback } from "react";
import { TabGroup } from "@/components/ui/tab-group";
import { StrategyBuilder, type BacktestConfig } from "./components/strategy-builder";
import { BacktestQueue, type QueueJob } from "./components/backtest-queue";
import { BacktestResults } from "./components/backtest-results";
import { BacktestHistory } from "./components/backtest-history";
import { useRunBacktest } from "@/hooks/use-backtest";
import { type BacktestResult } from "@/lib/api-client";

/* ---------- Tabs ---------- */

const TABS = [
  { key: "builder", label: "策略建構" },
  { key: "queue", label: "回測佇列" },
  { key: "results", label: "回測結果" },
  { key: "history", label: "歷史紀錄" },
];

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
    <div className="p-3 md:p-4 max-w-[1440px] mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-4">
        <h1 className="text-xl md:text-2xl font-bold text-[var(--foreground)] tracking-tight">
          策略回測
        </h1>
        <TabGroup tabs={TABS} active={activeTab} onChange={setActiveTab} size="sm" />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-lg">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Loading overlay for run mutation */}
      {runMutation.isPending && activeTab === "results" && (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-[var(--accent-blue)]/30 border-t-[var(--accent-blue)] rounded-full animate-spin" />
            <span className="text-[var(--text-muted)] text-sm">回測執行中...</span>
          </div>
        </div>
      )}

      {/* Tab content */}
      <div className={runMutation.isPending && activeTab === "results" ? "hidden" : ""}>
        {activeTab === "builder" && (
          <div className="max-w-2xl">
            <StrategyBuilder onEnqueue={handleEnqueue} onRunNow={handleRunNow} />
          </div>
        )}

        {activeTab === "queue" && (
          <BacktestQueue
            jobs={queueJobs.length > 0 ? queueJobs : undefined}
            onCancel={handleCancelJob}
            onViewResult={handleViewResult}
          />
        )}

        {activeTab === "results" && <BacktestResults result={result} />}

        {activeTab === "history" && <BacktestHistory />}
      </div>
    </div>
  );
}
