"use client";

import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";

/* ---------- Types ---------- */

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface QueueJob {
  id: string;
  symbol: string;
  strategy: string;
  status: JobStatus;
  progress: number;
  createdAt: string;
  error?: string;
}

interface BacktestQueueProps {
  jobs?: QueueJob[];
  onCancel?: (id: string) => void;
  onViewResult?: (id: string) => void;
}

/* ---------- Helpers ---------- */

const statusConfig: Record<
  JobStatus,
  { label: string; variant: "default" | "blue" | "score-excellent" | "score-poor"; pulse?: boolean }
> = {
  pending: { label: "等待中", variant: "default" },
  running: { label: "執行中", variant: "blue", pulse: true },
  completed: { label: "完成", variant: "score-excellent" },
  failed: { label: "失敗", variant: "score-poor" },
};

/* ---------- Mock Data ---------- */

function generateMockJobs(): QueueJob[] {
  return [
    {
      id: "q-001",
      symbol: "2330.TW",
      strategy: "RSI Mean Reversion",
      status: "completed",
      progress: 100,
      createdAt: "2026-04-30 14:30",
    },
    {
      id: "q-002",
      symbol: "AAPL",
      strategy: "MACD Crossover",
      status: "running",
      progress: 67,
      createdAt: "2026-04-30 14:32",
    },
    {
      id: "q-003",
      symbol: "2454.TW",
      strategy: "Bollinger Breakout",
      status: "pending",
      progress: 0,
      createdAt: "2026-04-30 14:33",
    },
    {
      id: "q-004",
      symbol: "TSLA",
      strategy: "RSI Mean Reversion",
      status: "failed",
      progress: 23,
      createdAt: "2026-04-30 14:28",
      error: "Insufficient price data",
    },
  ];
}

/* ---------- Component ---------- */

export function BacktestQueue({
  jobs: externalJobs,
  onCancel,
  onViewResult,
}: BacktestQueueProps) {
  const [mockJobs, setMockJobs] = useState<QueueJob[]>(generateMockJobs);
  const jobs = externalJobs || mockJobs;

  const hasRunning = jobs.some((j) => j.status === "running");

  // Simulate progress for running jobs
  const tickProgress = useCallback(() => {
    setMockJobs((prev) =>
      prev.map((job) => {
        if (job.status !== "running") return job;
        const next = Math.min(100, job.progress + Math.floor(Math.random() * 8) + 2);
        if (next >= 100) {
          return { ...job, progress: 100, status: "completed" as JobStatus };
        }
        return { ...job, progress: next };
      })
    );
  }, []);

  useEffect(() => {
    if (!hasRunning || externalJobs) return;
    const interval = setInterval(tickProgress, 3000);
    return () => clearInterval(interval);
  }, [hasRunning, externalJobs, tickProgress]);

  // Promote pending to running when no running job exists
  useEffect(() => {
    if (externalJobs) return;
    setMockJobs((prev) => {
      const running = prev.find((j) => j.status === "running");
      if (running) return prev;
      const firstPending = prev.findIndex((j) => j.status === "pending");
      if (firstPending === -1) return prev;
      return prev.map((j, i) =>
        i === firstPending ? { ...j, status: "running" as JobStatus } : j
      );
    });
  }, [jobs, externalJobs]);

  const handleCancel = (id: string) => {
    if (onCancel) {
      onCancel(id);
    } else {
      setMockJobs((prev) => prev.filter((j) => j.id !== id));
    }
  };

  if (jobs.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <div className="text-center">
          <p className="text-[var(--text-muted)] text-sm mb-1">佇列為空</p>
          <p className="text-[var(--text-muted)] text-xs">
            在策略建構頁面新增回測任務
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
        <span>
          共 <span className="mono-nums text-white">{jobs.length}</span> 個任務
        </span>
        <span>
          執行中{" "}
          <span className="mono-nums text-[var(--accent-blue)]">
            {jobs.filter((j) => j.status === "running").length}
          </span>
        </span>
        <span>
          完成{" "}
          <span className="mono-nums text-[var(--stock-down)]">
            {jobs.filter((j) => j.status === "completed").length}
          </span>
        </span>
      </div>

      {/* Job list */}
      <div className="space-y-2">
        {jobs.map((job) => {
          const config = statusConfig[job.status];
          return (
            <div
              key={job.id}
              className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 transition-all duration-200 hover:bg-[var(--card-hover)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-white mono-nums">
                      {job.symbol}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      {job.strategy}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge
                      variant={config.variant}
                      className={config.pulse ? "animate-pulse" : ""}
                    >
                      {config.label}
                    </Badge>
                    <span className="text-[10px] text-[var(--text-muted)] mono-nums">
                      {job.createdAt}
                    </span>
                  </div>
                  {job.error && (
                    <p className="text-[10px] text-red-400 mt-1">{job.error}</p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {job.status === "completed" && (
                    <button
                      onClick={() => onViewResult?.(job.id)}
                      className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-[var(--accent-blue)]/10 border border-[var(--accent-blue)]/30 text-[var(--accent-blue)] hover:bg-[var(--accent-blue)]/20 transition-all duration-200"
                    >
                      查看結果
                    </button>
                  )}
                  {job.status === "pending" && (
                    <button
                      onClick={() => handleCancel(job.id)}
                      className="px-2.5 py-1 rounded-md text-[10px] font-medium bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 text-red-400 hover:bg-[var(--stock-up)]/20 transition-all duration-200"
                    >
                      取消
                    </button>
                  )}
                </div>
              </div>

              {/* Progress bar for running jobs */}
              {(job.status === "running" || (job.status === "completed" && job.progress === 100)) && (
                <div className="mt-3">
                  <div className="flex justify-between text-[10px] text-[var(--text-muted)] mb-1">
                    <span>進度</span>
                    <span className="mono-nums">{job.progress}%</span>
                  </div>
                  <div className="h-1.5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        job.status === "completed"
                          ? "bg-[var(--stock-down)]"
                          : "bg-[var(--accent-blue)]"
                      }`}
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
