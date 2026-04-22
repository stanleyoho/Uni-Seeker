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

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-400">Logic:</span>
        <button
          type="button"
          onClick={() => onLogicChange("AND")}
          className={`px-3 py-1 rounded text-sm ${logicOperator === "AND" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"}`}
        >
          AND
        </button>
        <button
          type="button"
          onClick={() => onLogicChange("OR")}
          className={`px-3 py-1 rounded text-sm ${logicOperator === "OR" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"}`}
        >
          OR
        </button>
      </div>

      {conditions.map((cond, i) => (
        <div key={i} className="flex items-center gap-2 flex-wrap">
          <select
            value={cond.indicator}
            onChange={(e) => updateCondition(i, "indicator", e.target.value)}
            className="px-3 py-2 rounded bg-gray-800 border border-gray-700 text-white text-sm"
          >
            {indicators.map((ind) => (
              <option key={ind} value={ind}>
                {ind}
              </option>
            ))}
          </select>

          <select
            value={cond.op}
            onChange={(e) => updateCondition(i, "op", e.target.value)}
            className="px-3 py-2 rounded bg-gray-800 border border-gray-700 text-white text-sm"
          >
            {OPERATORS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>

          <input
            type="number"
            value={String(cond.value)}
            onChange={(e) => updateCondition(i, "value", Number(e.target.value))}
            className="w-24 px-3 py-2 rounded bg-gray-800 border border-gray-700 text-white text-sm"
            placeholder="Value"
          />

          <button
            type="button"
            onClick={() => removeCondition(i)}
            className="text-red-500 hover:text-red-400 text-sm px-2"
          >
            Remove
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={addCondition}
        className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-sm"
      >
        + Add Condition
      </button>
    </div>
  );
}
