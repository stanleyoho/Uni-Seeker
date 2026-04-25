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

  const selectClass =
    "px-3 py-2 rounded-lg bg-[var(--card-bg)] border border-[var(--border-color)] text-white text-sm focus:outline-none focus:border-[var(--accent-blue)] transition-all duration-200";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-[var(--text-muted)]">Logic:</span>
        <div className="flex bg-[var(--bg-secondary)] p-0.5 rounded-lg">
          <button
            type="button"
            onClick={() => onLogicChange("AND")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
              logicOperator === "AND"
                ? "bg-[var(--accent-blue)] text-white shadow-sm"
                : "text-[var(--text-secondary)] hover:text-white"
            }`}
          >
            AND
          </button>
          <button
            type="button"
            onClick={() => onLogicChange("OR")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200 ${
              logicOperator === "OR"
                ? "bg-[var(--accent-blue)] text-white shadow-sm"
                : "text-[var(--text-secondary)] hover:text-white"
            }`}
          >
            OR
          </button>
        </div>
      </div>

      {conditions.map((cond, i) => (
        <div
          key={i}
          className="flex items-center gap-2 flex-wrap p-3 bg-[var(--bg-secondary)] rounded-xl border border-[var(--border-color)] animate-fade-in"
        >
          <select value={cond.indicator} onChange={(e) => updateCondition(i, "indicator", e.target.value)} className={selectClass}>
            {indicators.map((ind) => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>

          <select value={cond.op} onChange={(e) => updateCondition(i, "op", e.target.value)} className={`${selectClass} font-mono`}>
            {OPERATORS.map((op) => (
              <option key={op} value={op}>{op}</option>
            ))}
          </select>

          <input
            type="number"
            value={String(cond.value)}
            onChange={(e) => updateCondition(i, "value", Number(e.target.value))}
            className={`w-24 ${selectClass} font-mono`}
            placeholder="Value"
          />

          <button
            type="button"
            onClick={() => removeCondition(i)}
            className="text-[var(--text-muted)] hover:text-red-400 transition-all duration-200 text-sm px-2 py-1 rounded-lg hover:bg-red-500/10"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={addCondition}
        className="flex items-center gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] border border-dashed border-[var(--border-color)] text-[var(--text-secondary)] rounded-xl hover:border-[var(--accent-blue)]/50 hover:text-white hover:bg-[var(--card-hover)] transition-all duration-200 text-sm"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add Condition
      </button>
    </div>
  );
}
