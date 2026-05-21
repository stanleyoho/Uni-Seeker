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
import { AmbientBackground } from "@/components/stratos/ambient";
import { LoadingSpinner } from "@/components/ui/loading";

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

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* LEFT: Conditions panel (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <GlassPanel title="Screen Configurations">
              {/* Preset buttons - compact grid */}
              <div className="mb-6">
                <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                  {t.screener?.presets ?? "STRATEGY PRESETS"}
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  {PRESETS.map((preset) => (
                    <button
                      key={preset.key}
                      onClick={() => applyPreset(preset)}
                      className="px-3 py-2 text-[11px] font-bold text-left transition-all duration-200 border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--foreground)] active:scale-95"
                      style={{ clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))" }}
                    >
                      {preset.label[locale as keyof typeof preset.label] || preset.label.en}
                    </button>
                  ))}
                </div>
              </div>

              {/* Saved screens */}
              {savedScreens.items.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                    {t.screener?.saved ?? "SAVED QUERIES"}
                  </h4>
                  <div className="flex gap-2 flex-wrap">
                    {savedScreens.items.map((screen) => (
                      <div key={screen.id} className="group relative">
                        <button
                          onClick={() => {
                            setConditions(screen.conditions);
                            setLogicOp(screen.operator);
                            setError(null);
                          }}
                          className="px-3 py-1.5 text-[10px] font-bold border border-[var(--border-subtle)] bg-[var(--card-hover)] text-[var(--text-secondary)] hover:border-[var(--accent-cyan)] hover:text-[var(--foreground)] transition-all"
                        >
                          {screen.name.toUpperCase()}
                        </button>
                        <button
                          onClick={() => savedScreens.remove(screen.id)}
                          className="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full w-4 h-4 flex items-center justify-center text-[8px] opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Condition builder */}
              <div className="mb-6">
                <ConditionBuilder
                  conditions={conditions}
                  onChange={setConditions}
                  logicOperator={logicOp}
                  onLogicChange={setLogicOp}
                />
              </div>

              {/* Controls */}
              <div className="flex flex-col gap-4 pt-4 border-t border-[var(--border-subtle)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[var(--text-secondary)]">{t.screener.limit.toUpperCase()}</span>
                  <input
                    type="number"
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value) || 50)}
                    className="w-20 px-3 py-1.5 text-sm font-bold bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] focus:border-[var(--accent-cyan)] focus:outline-none transition-all tabular-nums"
                  />
                </div>
                
                <div className="flex gap-2">
                  <ClippedButton
                    variant="red-solid"
                    size="md"
                    className="flex-1"
                    onClick={handleScreen}
                    disabled={loading}
                  >
                    {loading ? "SCANNING..." : t.screener.screen.toUpperCase()}
                  </ClippedButton>
                  
                  {conditions.length > 0 && !showSave && (
                    <ClippedButton
                      variant="cyan-ghost"
                      size="md"
                      onClick={() => setShowSave(true)}
                    >
                      SAVE
                    </ClippedButton>
                  )}
                </div>

                {showSave && (
                  <div className="flex flex-col gap-2 p-3 bg-[var(--card-hover)] border border-[var(--accent-cyan)]/30 animate-fade-in">
                    <input
                      type="text"
                      value={saveName}
                      onChange={(e) => setSaveName(e.target.value)}
                      placeholder="ENTER SCREEN NAME"
                      className="w-full px-3 py-2 text-xs font-bold bg-[var(--background)] border border-[var(--border-subtle)] text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none"
                    />
                    <div className="flex gap-2">
                      <button 
                        onClick={() => {
                          if (saveName.trim()) {
                            savedScreens.save(saveName.trim(), conditions, logicOp);
                            setSaveName("");
                            setShowSave(false);
                          }
                        }}
                        className="flex-1 py-1.5 bg-[var(--accent-cyan)] text-black text-[10px] font-bold"
                      >
                        CONFIRM
                      </button>
                      <button 
                        onClick={() => setShowSave(false)}
                        className="px-4 py-1.5 border border-[var(--border-subtle)] text-[var(--text-muted)] text-[10px] font-bold"
                      >
                        CANCEL
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Error */}
              {error && (
                <div className="mt-4 px-3 py-2 bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold tracking-wider">
                  ERROR: {error.toUpperCase()}
                </div>
              )}
            </GlassPanel>
          </div>

          {/* RIGHT: Results panel (8 cols) */}
          <div className="lg:col-span-8">
            <GlassPanel title={`${t.screener?.resultsTitle ?? "SCREENING RESULTS"} ${total > 0 ? `[${total}]` : ""}`} noPadding>
              <div className="min-h-[600px]">
                {loading ? (
                  <div className="h-full flex flex-center items-center justify-center pt-20">
                    <LoadingSpinner />
                  </div>
                ) : (
                  <ResultsTable results={results} total={total} />
                )}
              </div>
            </GlassPanel>
          </div>
        </div>
      </main>
    </div>
  );
}
