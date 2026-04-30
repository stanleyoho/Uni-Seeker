"use client";

import { useState, useEffect, useCallback } from "react";

export interface ParamRange {
  min: number;
  max: number;
  step: number;
}

interface ParamGridBuilderProps {
  params: Record<string, unknown>;
  onChange: (ranges: Record<string, ParamRange>) => void;
}

const inputClass =
  "w-full px-2 py-1.5 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] text-xs mono-nums placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

function getDefaultValue(val: unknown): number {
  if (typeof val === "number") return val;
  return 0;
}

export function ParamGridBuilder({ params, onChange }: ParamGridBuilderProps) {
  const paramKeys = Object.keys(params);

  const [ranges, setRanges] = useState<Record<string, ParamRange>>(() => {
    const initial: Record<string, ParamRange> = {};
    for (const key of paramKeys) {
      const base = getDefaultValue(params[key]);
      initial[key] = {
        min: Math.max(0, base - Math.ceil(base * 0.5)),
        max: base + Math.ceil(base * 0.5),
        step: Math.max(1, Math.floor(base * 0.1)),
      };
    }
    return initial;
  });

  const stableOnChange = useCallback(onChange, [onChange]);

  useEffect(() => {
    stableOnChange(ranges);
  }, [ranges, stableOnChange]);

  const updateRange = (key: string, field: keyof ParamRange, value: number) => {
    setRanges((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }));
  };

  // Calculate total combinations
  const totalCombinations = paramKeys.reduce((acc, key) => {
    const r = ranges[key];
    if (!r || r.step <= 0 || r.max <= r.min) return acc;
    const count = Math.floor((r.max - r.min) / r.step) + 1;
    return acc * count;
  }, 1);

  if (paramKeys.length === 0) {
    return (
      <p className="text-[var(--text-muted)] text-xs">
        此策略無可調參數
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3">
        {paramKeys.map((key) => (
          <div
            key={key}
            className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3"
          >
            <p className="text-xs font-medium text-[var(--foreground)] mb-2">{key}</p>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
                  Min
                </label>
                <input
                  type="number"
                  value={ranges[key]?.min ?? 0}
                  onChange={(e) =>
                    updateRange(key, "min", Number(e.target.value))
                  }
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
                  Max
                </label>
                <input
                  type="number"
                  value={ranges[key]?.max ?? 0}
                  onChange={(e) =>
                    updateRange(key, "max", Number(e.target.value))
                  }
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
                  Step
                </label>
                <input
                  type="number"
                  value={ranges[key]?.step ?? 1}
                  onChange={(e) =>
                    updateRange(key, "step", Number(e.target.value))
                  }
                  className={inputClass}
                  min={1}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 px-1">
        <div className="w-2 h-2 rounded-full bg-[var(--accent-blue)]" />
        <p className="text-xs text-[var(--text-secondary)]">
          將測試{" "}
          <span className="mono-nums text-[var(--foreground)] font-semibold">
            {totalCombinations.toLocaleString()}
          </span>{" "}
          種參數組合
        </p>
      </div>
    </div>
  );
}
