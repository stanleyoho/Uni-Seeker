"use client";

import { useState } from "react";
import { ConditionBuilder } from "@/components/screener/condition-builder";
import { ResultsTable } from "@/components/screener/results-table";
import {
  screenStocks,
  type ScreenCondition,
  type ScreenResult,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

const PRESETS = [
  {
    key: "oversold",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
      </svg>
    ),
    conditions: [{ indicator: "RSI", params: {}, op: "<", value: 30 }] as ScreenCondition[],
  },
  {
    key: "overbought",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
    conditions: [{ indicator: "RSI", params: {}, op: ">", value: 70 }] as ScreenCondition[],
  },
  {
    key: "goldenCross",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    conditions: [
      { indicator: "SMA", params: { period: 50 }, op: ">", value: 0 },
      { indicator: "SMA", params: { period: 200 }, op: "<", value: 0 },
    ] as ScreenCondition[],
  },
];

const presetLabels: Record<string, Record<string, string>> = {
  oversold: { en: "Oversold (RSI < 30)", "zh-TW": "超賣 (RSI < 30)" },
  overbought: { en: "Overbought (RSI > 70)", "zh-TW": "超買 (RSI > 70)" },
  goldenCross: { en: "Golden Cross", "zh-TW": "黃金交叉" },
};

export default function ScreenerPage() {
  const { t, locale } = useI18n();
  const [conditions, setConditions] = useState<ScreenCondition[]>([]);
  const [logicOp, setLogicOp] = useState<"AND" | "OR">("AND");
  const [results, setResults] = useState<ScreenResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);

  const handleScreen = async () => {
    if (conditions.length === 0) {
      setError(t.screener.addAtLeastOne);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await screenStocks(conditions, logicOp, undefined, limit);
      setResults(res.results);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Screen request failed");
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    setConditions(preset.conditions);
    setError(null);
  };

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-white tracking-tight">{t.screener.title}</h1>

      {/* Preset strategy cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            onClick={() => applyPreset(preset)}
            className="group flex items-center gap-3 bg-[#1a2332] border border-[#1e293b] rounded-xl p-4 text-left transition-all duration-200 hover:border-blue-500/30 hover:bg-[#1e293b]"
          >
            <div className="text-blue-400 group-hover:text-blue-300 transition-colors duration-200">
              {preset.icon}
            </div>
            <span className="text-sm font-medium text-[#94a3b8] group-hover:text-white transition-colors duration-200">
              {presetLabels[preset.key][locale] || presetLabels[preset.key].en}
            </span>
          </button>
        ))}
      </div>

      {/* Condition builder */}
      <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5 mb-6">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.screener.conditions}</h2>
        <ConditionBuilder
          conditions={conditions}
          onChange={setConditions}
          logicOperator={logicOp}
          onLogicChange={setLogicOp}
        />

        <div className="flex items-center gap-4 mt-5 pt-4 border-t border-[#1e293b]">
          <label className="text-sm text-[#94a3b8] flex items-center gap-2">
            {t.screener.limit}:
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 50)}
              className="w-20 px-2.5 py-1.5 rounded-lg bg-[#111827] border border-[#1e293b] text-white text-sm focus:outline-none focus:border-blue-500 transition-all duration-200"
            />
          </label>
          <button
            onClick={handleScreen}
            disabled={loading}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all duration-200 disabled:opacity-50 font-medium shadow-lg shadow-blue-600/20"
          >
            {loading ? t.screener.screening : t.screener.screen}
          </button>
        </div>

        {error && (
          <div className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
      </div>

      {/* Results */}
      <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.screener.results}</h2>
        <ResultsTable results={results} total={total} />
      </div>
    </div>
  );
}
