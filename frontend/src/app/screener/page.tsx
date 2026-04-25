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
import { useSavedScreens } from "@/hooks/use-saved-screens";

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
  {
    key: "highVolume",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0" />
      </svg>
    ),
    conditions: [{ indicator: "VOLUME", params: {}, op: ">", value: 10000000 }] as ScreenCondition[],
  },
  {
    key: "bollingerSqueeze",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
      </svg>
    ),
    conditions: [{ indicator: "BOLLINGER", params: { period: 20 }, op: "<", value: 0.05 }] as ScreenCondition[],
  },
  {
    key: "kdOversold",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
    ),
    conditions: [{ indicator: "KD", params: {}, op: "<", value: 20 }] as ScreenCondition[],
  },
];

const presetLabels: Record<string, Record<string, string>> = {
  oversold: { en: "Oversold (RSI < 30)", "zh-TW": "超賣 (RSI < 30)" },
  overbought: { en: "Overbought (RSI > 70)", "zh-TW": "超買 (RSI > 70)" },
  goldenCross: { en: "Golden Cross", "zh-TW": "黃金交叉" },
  highVolume: { en: "High Volume (>10M)", "zh-TW": "大量 (>1000萬)" },
  bollingerSqueeze: { en: "Bollinger Squeeze", "zh-TW": "布林收斂" },
  kdOversold: { en: "KD Oversold (<20)", "zh-TW": "KD 超賣 (<20)" },
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
  const [saveName, setSaveName] = useState("");
  const [showSave, setShowSave] = useState(false);
  const savedScreens = useSavedScreens();

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
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            onClick={() => applyPreset(preset)}
            className="group flex items-center gap-3 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl p-4 text-left transition-all duration-200 hover:border-[var(--accent-blue)]/30 hover:bg-[var(--card-hover)]"
          >
            <div className="text-[var(--accent-blue)] group-hover:text-blue-300 transition-colors duration-200">
              {preset.icon}
            </div>
            <span className="text-sm font-medium text-[var(--text-secondary)] group-hover:text-white transition-colors duration-200">
              {presetLabels[preset.key][locale] || presetLabels[preset.key].en}
            </span>
          </button>
        ))}
      </div>

      {/* Saved screens */}
      {savedScreens.items.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-2">
            {t.screener?.saved ?? "Saved Screens"}
          </h3>
          <div className="flex gap-2 flex-wrap">
            {savedScreens.items.map((screen) => (
              <div key={screen.id} className="flex items-center gap-1">
                <button
                  onClick={() => {
                    setConditions(screen.conditions);
                    setLogicOp(screen.operator);
                    setError(null);
                  }}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--card-bg)] border border-[var(--border-color)] text-[var(--text-secondary)] hover:text-white hover:border-[var(--accent-blue)]/30 transition-all"
                >
                  {screen.name}
                </button>
                <button
                  onClick={() => savedScreens.remove(screen.id)}
                  className="text-[var(--text-muted)] hover:text-red-400 transition-colors p-0.5"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Condition builder */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl p-5 mb-6">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.screener.conditions}</h2>
        <ConditionBuilder
          conditions={conditions}
          onChange={setConditions}
          logicOperator={logicOp}
          onLogicChange={setLogicOp}
        />

        <div className="flex items-center gap-4 mt-5 pt-4 border-t border-[var(--border-color)]">
          <label className="text-sm text-[var(--text-secondary)] flex items-center gap-2">
            {t.screener.limit}:
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 50)}
              className="w-20 px-2.5 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)] text-white text-sm focus:outline-none focus:border-[var(--accent-blue)] transition-all duration-200"
            />
          </label>
          <button
            onClick={handleScreen}
            disabled={loading}
            className="px-6 py-2.5 bg-[var(--accent-blue)] text-white rounded-xl hover:bg-[var(--accent-blue-hover)] transition-all duration-200 disabled:opacity-50 font-medium shadow-lg shadow-blue-600/20"
          >
            {loading ? t.screener.screening : t.screener.screen}
          </button>

          {/* Save button */}
          {conditions.length > 0 && (
            showSave ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && saveName.trim()) {
                      savedScreens.save(saveName.trim(), conditions, logicOp);
                      setSaveName("");
                      setShowSave(false);
                    }
                  }}
                  placeholder={t.screener?.saveNamePlaceholder ?? "Screen name..."}
                  className="px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)] text-white text-sm focus:outline-none focus:border-[var(--accent-blue)] transition-all w-36"
                  autoFocus
                />
                <button
                  onClick={() => {
                    if (saveName.trim()) {
                      savedScreens.save(saveName.trim(), conditions, logicOp);
                      setSaveName("");
                      setShowSave(false);
                    }
                  }}
                  className="px-3 py-2 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700 transition-all"
                >
                  {t.screener?.saveConfirm ?? "Save"}
                </button>
                <button
                  onClick={() => setShowSave(false)}
                  className="text-[var(--text-muted)] hover:text-white transition-colors text-sm"
                >
                  {t.screener?.cancel ?? "Cancel"}
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowSave(true)}
                className="px-4 py-2.5 text-sm text-[var(--text-secondary)] border border-[var(--border-color)] rounded-xl hover:text-white hover:border-[var(--accent-blue)]/30 transition-all"
              >
                {t.screener?.save ?? "Save Screen"}
              </button>
            )
          )}
        </div>

        {error && (
          <div className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
      </div>

      {/* Results */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl p-5">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.screener.results}</h2>
        <ResultsTable results={results} total={total} />
      </div>
    </div>
  );
}
