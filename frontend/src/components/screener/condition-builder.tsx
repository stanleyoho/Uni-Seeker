"use client";

import { useState, useEffect } from "react";
import { fetchIndicatorList, type ScreenCondition } from "@/lib/api-client";

const OPERATORS = [">", ">=", "<", "<=", "=="];

interface ConditionBuilderProps {
  conditions: ScreenCondition[];
  onChange: (conditions: ScreenCondition[]) => void;
  logicOperator: "AND" | "OR";
  onLogicChange: (op: "AND" | "OR") => void;
}

export function ConditionBuilder({
  conditions,
  onChange,
  logicOperator,
  onLogicChange,
}: ConditionBuilderProps) {
  const [indicators, setIndicators] = useState<string[]>([]);

  useEffect(() => {
    fetchIndicatorList()
      .then(setIndicators)
      .catch(() => setIndicators(["RSI", "MACD", "SMA", "EMA", "BBANDS"]));
  }, []);

  const addCondition = () => {
    onChange([
      ...conditions,
      { indicator: indicators[0] || "RSI", params: {}, op: ">", value: 0 },
    ]);
  };

  const removeCondition = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  const updateCondition = (index: number, field: keyof ScreenCondition, val: unknown) => {
    const updated = conditions.map((c, i) => {
      if (i !== index) return c;
      return { ...c, [field]: val };
    });
    onChange(updated);
  };

  const inputClass =
    "px-3 py-1.5 bg-[var(--card-bg)] border border-[var(--border-subtle)] text-[var(--foreground)] text-xs font-bold focus:outline-none focus:border-[var(--accent-cyan)] transition-all";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Logic Flow</span>
        <div className="flex bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-0.5">
          <button
            type="button"
            onClick={() => onLogicChange("AND")}
            className={`px-4 py-1 text-[10px] font-bold transition-all ${
              logicOperator === "AND"
                ? "bg-[var(--accent-primary)] text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--foreground)]"
            }`}
          >
            AND
          </button>
          <button
            type="button"
            onClick={() => onLogicChange("OR")}
            className={`px-4 py-1 text-[10px] font-bold transition-all ${
              logicOperator === "OR"
                ? "bg-[var(--accent-primary)] text-white"
                : "text-[var(--text-secondary)] hover:text-[var(--foreground)]"
            }`}
          >
            OR
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {conditions.map((cond, i) => (
          <div
            key={i}
            className="flex items-center gap-2 flex-wrap p-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] animate-fade-in relative group"
          >
            <select 
              value={cond.indicator} 
              onChange={(e) => updateCondition(i, "indicator", e.target.value)} 
              className={`${inputClass} flex-1 min-w-[120px]`}
            >
              {indicators.map((ind) => (
                <option key={ind} value={ind}>{ind}</option>
              ))}
            </select>

            <select 
              value={cond.op} 
              onChange={(e) => updateCondition(i, "op", e.target.value)} 
              className={`${inputClass} w-16 font-mono`}
            >
              {OPERATORS.map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>

            <input
              type="number"
              value={String(cond.value)}
              onChange={(e) => updateCondition(i, "value", Number(e.target.value))}
              className={`w-24 ${inputClass} font-mono`}
              placeholder="VALUE"
            />

            <button
              type="button"
              onClick={() => removeCondition(i)}
              className="text-[var(--text-muted)] hover:text-red-500 transition-all p-1.5 bg-[var(--card-hover)] border border-[var(--border-subtle)]"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addCondition}
        className="w-full flex items-center justify-center gap-2 py-2 border border-dashed border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--accent-cyan)]/50 hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-all text-[10px] font-bold uppercase tracking-widest"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add Condition
      </button>
    </div>
  );
}
