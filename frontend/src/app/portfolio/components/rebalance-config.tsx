"use client";

import type { RebalanceMode } from "@/hooks/use-portfolio";

interface RebalanceConfigProps {
  mode: RebalanceMode;
  onModeChange: (mode: RebalanceMode) => void;
  periodDays: number;
  onPeriodDaysChange: (days: number) => void;
  thresholdPct: number;
  onThresholdPctChange: (pct: number) => void;
  initialCapital: number;
  onInitialCapitalChange: (capital: number) => void;
}

const modes: { key: RebalanceMode; label: string }[] = [
  { key: "none", label: "不再平衡" },
  { key: "periodic", label: "定期" },
  { key: "threshold", label: "偏離" },
];

export function RebalanceConfig({
  mode,
  onModeChange,
  periodDays,
  onPeriodDaysChange,
  thresholdPct,
  onThresholdPctChange,
  initialCapital,
  onInitialCapitalChange,
}: RebalanceConfigProps) {
  const inputClass =
    "w-full px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-white text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

  return (
    <div className="space-y-3">
      {/* Mode selector */}
      <div>
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1.5">
          再平衡模式
        </label>
        <div className="flex gap-1 bg-[var(--bg-secondary)] p-1 rounded-xl">
          {modes.map((m) => (
            <button
              key={m.key}
              onClick={() => onModeChange(m.key)}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200 ${
                mode === m.key
                  ? "bg-[var(--accent-blue)] text-white shadow-lg shadow-[var(--accent-blue-glow)]"
                  : "text-[var(--text-secondary)] hover:text-white hover:bg-[var(--card-hover)]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Periodic config */}
      {mode === "periodic" && (
        <div className="animate-fade-in">
          <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
            再平衡週期 (天)
          </label>
          <input
            type="number"
            min={1}
            max={365}
            value={periodDays}
            onChange={(e) => onPeriodDaysChange(Math.max(1, Number(e.target.value) || 1))}
            className={`${inputClass} mono-nums`}
          />
        </div>
      )}

      {/* Threshold config */}
      {mode === "threshold" && (
        <div className="animate-fade-in">
          <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
            偏離閾值 (%)
          </label>
          <input
            type="number"
            min={1}
            max={50}
            value={thresholdPct}
            onChange={(e) => onThresholdPctChange(Math.max(1, Number(e.target.value) || 1))}
            className={`${inputClass} mono-nums`}
          />
        </div>
      )}

      {/* Initial capital */}
      <div>
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
          初始資金
        </label>
        <input
          type="number"
          value={initialCapital}
          onChange={(e) => onInitialCapitalChange(Number(e.target.value) || 0)}
          className={`${inputClass} mono-nums`}
        />
      </div>
    </div>
  );
}
