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
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";

const PRESETS = [
  {
    key: "oversold",
    label: { en: "RSI Oversold", "zh-TW": "RSI超賣" },
    conditions: [{ indicator: "RSI", params: {}, op: "<", value: 30 }] as ScreenCondition[],
  },
  {
    key: "overbought",
    label: { en: "RSI Overbought", "zh-TW": "RSI超買" },
    conditions: [{ indicator: "RSI", params: {}, op: ">", value: 70 }] as ScreenCondition[],
  },
  {
    key: "goldenCross",
    label: { en: "SMA Golden Cross", "zh-TW": "SMA金叉" },
    conditions: [
      { indicator: "SMA", params: { period: 50 }, op: ">", value: 0 },
      { indicator: "SMA", params: { period: 200 }, op: "<", value: 0 },
    ] as ScreenCondition[],
  },
  {
    key: "highVolume",
    label: { en: "Volume Breakout", "zh-TW": "量能突破" },
    conditions: [{ indicator: "VOLUME", params: {}, op: ">", value: 10000000 }] as ScreenCondition[],
  },
  {
    key: "bollingerSqueeze",
    label: { en: "BB Squeeze", "zh-TW": "布林收斂" },
    conditions: [{ indicator: "BOLLINGER", params: { period: 20 }, op: "<", value: 0.05 }] as ScreenCondition[],
  },
  {
    key: "kdOversold",
    label: { en: "KD Oversold", "zh-TW": "KD超賣" },
    conditions: [{ indicator: "KD", params: {}, op: "<", value: 20 }] as ScreenCondition[],
  },
];

export default function ResearchScreenerPage() {
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

  const inputStyle =
    "px-2.5 py-1.5 rounded-lg text-sm focus:outline-none focus:border-[var(--accent-primary)] transition-all duration-200";
  const inputBg: React.CSSProperties = {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    color: "var(--foreground)",
  };

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Side-by-side layout: Conditions (4col) | Results (8col) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* LEFT: Conditions panel (4 cols) */}
        <div className="lg:col-span-4">
          <GlassPanel title={t.screener?.conditions ?? "CONDITIONS"} className="h-full">
            {/* Preset buttons - compact grid */}
            <div className="mb-4">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider block mb-2"
                style={{ color: "var(--text-muted)" }}
              >
                {t.screener?.presets ?? "Presets"}
              </span>
              <div className="grid grid-cols-2 gap-1.5">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.key}
                    onClick={() => applyPreset(preset)}
                    className="px-2.5 py-1.5 text-xs font-medium text-left transition-all duration-150 hover:border-[var(--accent-primary)]/40 hover:bg-[var(--card-hover)]"
                    style={{
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-color)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {preset.label[locale as keyof typeof preset.label] || preset.label.en}
                  </button>
                ))}
              </div>
            </div>

            {/* Saved screens */}
            {savedScreens.items.length > 0 && (
              <div className="mb-4">
                <span
                  className="text-[10px] font-semibold uppercase tracking-wider block mb-2"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t.screener?.saved ?? "Saved"}
                </span>
                <div className="flex gap-1.5 flex-wrap">
                  {savedScreens.items.map((screen) => (
                    <div key={screen.id} className="flex items-center gap-0.5">
                      <button
                        onClick={() => {
                          setConditions(screen.conditions);
                          setLogicOp(screen.operator);
                          setError(null);
                        }}
                        className="px-2 py-1 text-[10px] font-medium text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:border-[var(--accent-primary)]/30 transition-all"
                        style={{
                          background: "var(--bg-secondary)",
                          border: "1px solid var(--border-color)",
                        }}
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
            <div className="mb-4">
              <ConditionBuilder
                conditions={conditions}
                onChange={setConditions}
                logicOperator={logicOp}
                onLogicChange={setLogicOp}
              />
            </div>

            {/* Controls */}
            <div
              className="flex flex-wrap items-center gap-3 pt-3"
              style={{ borderTop: "1px solid var(--border-color)" }}
            >
              <label className="text-xs text-[var(--text-secondary)] flex items-center gap-1.5">
                {t.screener.limit}:
                <input
                  type="number"
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value) || 50)}
                  className={`w-16 ${inputStyle}`}
                  style={inputBg}
                />
              </label>
              <ClippedButton
                variant="red-solid"
                size="md"
                onClick={handleScreen}
                disabled={loading}
              >
                {loading ? t.screener.screening : t.screener.screen}
              </ClippedButton>
            </div>

            {/* Save controls */}
            {conditions.length > 0 && (
              <div className="mt-3">
                {showSave ? (
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
                      className={`flex-1 min-w-0 ${inputStyle}`}
                      style={inputBg}
                      autoFocus
                    />
                    <ClippedButton
                      variant="green-solid"
                      size="sm"
                      onClick={() => {
                        if (saveName.trim()) {
                          savedScreens.save(saveName.trim(), conditions, logicOp);
                          setSaveName("");
                          setShowSave(false);
                        }
                      }}
                    >
                      {t.screener?.saveConfirm ?? "Save"}
                    </ClippedButton>
                    <button
                      onClick={() => setShowSave(false)}
                      className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors text-xs"
                    >
                      {t.screener?.cancel ?? "Cancel"}
                    </button>
                  </div>
                ) : (
                  <ClippedButton
                    variant="cyan-ghost"
                    size="sm"
                    onClick={() => setShowSave(true)}
                  >
                    {t.screener?.save ?? "Save Screen"}
                  </ClippedButton>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}
          </GlassPanel>
        </div>

        {/* RIGHT: Results panel (8 cols) */}
        <div className="lg:col-span-8">
          <GlassPanel title={`${t.screener?.resultsTitle ?? "RESULTS"} ${total > 0 ? `(${total})` : ""}`} className="h-full">
            <ResultsTable results={results} total={total} />
          </GlassPanel>
        </div>
      </div>
    </div>
  );
}
