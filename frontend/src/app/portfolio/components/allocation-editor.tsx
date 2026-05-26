"use client";

import type { PortfolioAllocation } from "@/hooks/use-portfolio";

interface AllocationEditorProps {
  allocations: PortfolioAllocation[];
  onChange: (allocations: PortfolioAllocation[]) => void;
  strategies: string[];
}

const STOCK_COLORS = [
  "#3b82f6", // blue
  "#8b5cf6", // purple
  "#f59e0b", // amber
  "#22c55e", // green
  "#ef4444", // red
];

const MAX_STOCKS = 5;

export function AllocationEditor({ allocations, onChange, strategies }: AllocationEditorProps) {
  const totalWeight = allocations.reduce((sum, a) => sum + a.weight, 0);
  const isValid = Math.abs(totalWeight - 100) < 0.01;

  // React Compiler memoises these automatically; hand-rolled
  // useCallback wrappers triggered react-hooks/preserve-manual-memoization
  // (the Compiler couldn't preserve the manual cache, which means it
  // bailed out of optimising the whole component). Plain functions
  // here give the Compiler the freedom to do its job.
  const addStock = () => {
    if (allocations.length >= MAX_STOCKS) return;
    onChange([
      ...allocations,
      { symbol: "", weight: 0, strategy: strategies[0] || "sma_cross" },
    ]);
  };

  const removeStock = (index: number) => {
    onChange(allocations.filter((_, i) => i !== index));
  };

  const updateAllocation = (
    index: number,
    patch: Partial<PortfolioAllocation>,
  ) => {
    onChange(allocations.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  };

  const autoDistribute = () => {
    if (allocations.length === 0) return;
    const w = Math.floor(100 / allocations.length);
    const remainder = 100 - w * allocations.length;
    onChange(
      allocations.map((a, i) => ({
        ...a,
        weight: w + (i === 0 ? remainder : 0),
      })),
    );
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

  return (
    <div className="space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">
          投資組合配置
        </label>
        <div className="flex gap-1.5">
          <button
            onClick={autoDistribute}
            disabled={allocations.length === 0}
            className="px-2 py-1 text-[10px] rounded-md bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-all duration-200 disabled:opacity-40"
          >
            均分權重
          </button>
          <button
            onClick={addStock}
            disabled={allocations.length >= MAX_STOCKS}
            className="px-2 py-1 text-[10px] rounded-md bg-[var(--accent-blue)]/10 border border-[var(--accent-blue)]/20 text-[var(--accent-blue)] hover:bg-[var(--accent-blue)]/20 transition-all duration-200 disabled:opacity-40"
          >
            + 新增標的
          </button>
        </div>
      </div>

      {/* Weight distribution bar */}
      {allocations.length > 0 && (
        <div className="h-2 rounded-full overflow-hidden flex bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
          {allocations.map((alloc, i) => (
            <div
              key={i}
              className="h-full transition-all duration-300 ease-out"
              style={{
                width: `${Math.max(alloc.weight, 0)}%`,
                backgroundColor: STOCK_COLORS[i % STOCK_COLORS.length],
                opacity: alloc.symbol ? 1 : 0.3,
              }}
            />
          ))}
          {totalWeight < 100 && (
            <div
              className="h-full"
              style={{
                width: `${100 - Math.min(totalWeight, 100)}%`,
                backgroundColor: "rgba(255,255,255,0.03)",
              }}
            />
          )}
        </div>
      )}

      {/* Weight total indicator */}
      {allocations.length > 0 && (
        <div className="flex items-center justify-end gap-1.5">
          <span
            className={`text-[10px] font-medium mono-nums ${
              isValid
                ? "text-[var(--stock-down)]"
                : totalWeight > 100
                  ? "text-[var(--stock-up)]"
                  : "text-[var(--amber)]"
            }`}
          >
            {totalWeight.toFixed(0)}% / 100%
          </span>
          {!isValid && (
            <span className="text-[10px] text-[var(--stock-up)]">
              {totalWeight > 100 ? "超過 100%" : "未達 100%"}
            </span>
          )}
        </div>
      )}

      {/* Allocation items */}
      <div className="space-y-2">
        {allocations.map((alloc, i) => (
          <div
            key={i}
            className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3 space-y-2 animate-fade-in"
          >
            {/* Top row: color dot + symbol + remove */}
            <div className="flex items-center gap-2">
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: STOCK_COLORS[i % STOCK_COLORS.length] }}
              />
              <input
                type="text"
                value={alloc.symbol}
                onChange={(e) =>
                  updateAllocation(i, { symbol: e.target.value.toUpperCase() })
                }
                placeholder="股票代號 (e.g. 2330.TW)"
                className="flex-1 px-2 py-1.5 rounded-md bg-[var(--background)] border border-[var(--border-subtle)] text-[var(--foreground)] text-xs placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200"
              />
              <button
                onClick={() => removeStock(i)}
                className="p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--stock-up)] hover:bg-[var(--stock-up)]/10 transition-all duration-200"
                aria-label={`移除 ${alloc.symbol || "標的"}`}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>

            {/* Weight slider */}
            <div className="flex items-center gap-3">
              <label className="text-[10px] text-[var(--text-muted)] w-8 shrink-0">權重</label>
              <input
                type="range"
                min="0"
                max="100"
                step="1"
                value={alloc.weight}
                onChange={(e) =>
                  updateAllocation(i, { weight: Number(e.target.value) })
                }
                className="flex-1 accent-blue-500 h-1.5"
                style={{
                  accentColor: STOCK_COLORS[i % STOCK_COLORS.length],
                }}
              />
              <span
                className="mono-nums text-xs font-medium w-10 text-right"
                style={{ color: STOCK_COLORS[i % STOCK_COLORS.length] }}
              >
                {alloc.weight}%
              </span>
            </div>

            {/* Strategy select */}
            <div className="flex items-center gap-3">
              <label className="text-[10px] text-[var(--text-muted)] w-8 shrink-0">策略</label>
              <select
                value={alloc.strategy}
                onChange={(e) => updateAllocation(i, { strategy: e.target.value })}
                className={`${inputClass} text-xs py-1.5`}
              >
                {strategies.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}
      </div>

      {/* Empty state */}
      {allocations.length === 0 && (
        <div className="text-center py-6">
          <p className="text-[var(--text-muted)] text-xs mb-2">尚未新增標的</p>
          <button
            onClick={addStock}
            className="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent-blue)]/10 border border-[var(--accent-blue)]/20 text-[var(--accent-blue)] hover:bg-[var(--accent-blue)]/20 transition-all duration-200"
          >
            + 新增第一檔標的
          </button>
        </div>
      )}
    </div>
  );
}
