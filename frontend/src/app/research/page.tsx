"use client";

import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
import { LoadingSpinner } from "@/components/ui/loading";
import { useRunScan, type SignalAction, type ScanResult } from "@/hooks/use-scanner";
import { SignalTable } from "@/app/scanner/components/signal-table";
import { downloadCSV } from "@/lib/csv-export";
import { CompareTabPanel } from "./components/compare-panel";

import {
  TEMPLATES,
  findTemplate,
  type StrategyConditionPreset,
  type BollingerParams,
  type KdParams,
  type MacdParams,
  type RsiParams,
  type SmaCrossParams,
  type VolumeParams,
} from "./templates";
import {
  INDICATOR_DOCS,
  INDICATOR_ORDER,
  type IndicatorKey,
} from "./indicator-docs";
import { IndicatorCard } from "./components/indicator-card";
import {
  BollingerInputs,
  KdInputs,
  MacdInputs,
  RsiInputs,
  SmaCrossInputs,
  VolumeInputs,
} from "./components/threshold-inputs";

// ---- Local form state ------------------------------------------------

interface ConditionEntry {
  enabled: boolean;
  rsi: RsiParams;
  macd: MacdParams;
  bollinger: BollingerParams;
  kd: KdParams;
  sma_cross: SmaCrossParams;
  volume: VolumeParams;
}

const DEFAULT_PARAMS: Omit<ConditionEntry, "enabled"> = {
  rsi: { op: "<", value: 30 },
  macd: { signal: "bullish_cross" },
  bollinger: { widthPct: 5, breakout: "upper" },
  kd: { op: "<", level: 30 },
  sma_cross: { shortPeriod: 5, longPeriod: 20 },
  volume: { multipleOf20dAvg: 1.5 },
};

type FormState = Record<IndicatorKey, ConditionEntry>;

function makeEmptyForm(): FormState {
  return INDICATOR_ORDER.reduce((acc, key) => {
    acc[key] = { enabled: false, ...DEFAULT_PARAMS };
    return acc;
  }, {} as FormState);
}

/**
 * Apply a template to a form-state by enabling the listed indicators
 * and overwriting the default params for each. Indicators not in the
 * template are reset to defaults + disabled. Exported for unit tests.
 */
export function applyTemplateToForm(
  presets: StrategyConditionPreset[],
): FormState {
  const next = makeEmptyForm();
  for (const p of presets) {
    const slot = next[p.indicator];
    slot.enabled = true;
    // Copy threshold params into the correct discriminated slot.
    switch (p.indicator) {
      case "rsi":
        slot.rsi = p.params as RsiParams;
        break;
      case "macd":
        slot.macd = p.params as MacdParams;
        break;
      case "bollinger":
        slot.bollinger = p.params as BollingerParams;
        break;
      case "kd":
        slot.kd = p.params as KdParams;
        break;
      case "sma_cross":
        slot.sma_cross = p.params as SmaCrossParams;
        break;
      case "volume":
        slot.volume = p.params as VolumeParams;
        break;
    }
  }
  return next;
}

/**
 * Convert the form state into the `strategy_keys[]` payload the backend
 * `POST /api/v1/scanner/scan` expects.
 *
 * BACKEND GAP: thresholds are NOT forwarded — the current
 * `SignalScanRequest` schema has no `thresholds` field. Indicators whose
 * `backendStrategyKey` is `null` (KD / Volume today) are skipped so the
 * scan does not 400 with "Unknown strategy keys".
 */
export function formToStrategyKeys(form: FormState): string[] {
  const keys: string[] = [];
  for (const key of INDICATOR_ORDER) {
    const entry = form[key];
    if (!entry.enabled) continue;
    const backendKey = INDICATOR_DOCS[key].backendStrategyKey;
    if (!backendKey) continue;
    if (!keys.includes(backendKey)) keys.push(backendKey);
  }
  return keys;
}

// ---- Page ------------------------------------------------------------

const ALL_ACTIONS: SignalAction[] = [
  "STRONG_BUY",
  "BUY",
  "HOLD",
  "SELL",
  "STRONG_SELL",
];

export default function UnifiedResearchPage() {
  // Route-consolidation: `/research/compare` was folded into this page
  // via `?tab=compare`. We read the live query so we can multiplex
  // which tab panel renders. Scan stays the default — any other
  // `tab=` value (or no query string) falls through to the scan
  // workflow below. We always render the page chrome
  // (AmbientBackground + `<main>` padding) so the SubTabs strip in
  // the layout sits above a consistent canvas regardless of which
  // tab is active.
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab");

  const [form, setForm] = useState<FormState>(() => makeEmptyForm());
  const [activeTemplate, setActiveTemplate] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState<SignalAction[]>([
    ...ALL_ACTIONS,
  ]);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const runScan = useRunScan();

  const enabledKeys = useMemo(() => formToStrategyKeys(form), [form]);
  const enabledCount = useMemo(
    () => INDICATOR_ORDER.filter((k) => form[k].enabled).length,
    [form],
  );

  const handleApplyTemplate = useCallback((templateId: string) => {
    const tpl = findTemplate(templateId);
    if (!tpl) return;
    setForm(applyTemplateToForm(tpl.strategies));
    setActiveTemplate(templateId);
  }, []);

  const updateEntry = useCallback(
    <K extends IndicatorKey>(key: K, patch: Partial<ConditionEntry>) => {
      setForm((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
      // Any manual edit drops us out of "matches a preset" state.
      setActiveTemplate(null);
    },
    [],
  );

  const handleScan = useCallback(() => {
    const keys = enabledKeys.length > 0 ? enabledKeys : undefined;
    runScan.mutate(keys, {
      onSuccess: (data) => setScanResult(data),
    });
  }, [enabledKeys, runScan]);

  const stocks = scanResult?.stocks ?? [];

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        {/* Tab multiplex: `?tab=compare` renders CompareTabPanel
            (extracted from the former `/research/compare` route);
            anything else falls through to the scan workflow below.
            The shared `<main>` chrome above keeps padding + ambient
            backdrop identical across tabs. */}
        {activeTab === "compare" ? (
          <CompareTabPanel />
        ) : (
        <>
        {/* ---- Template picker row ---- */}
        <GlassPanel title="STRATEGY TEMPLATES">
          <div className="flex flex-wrap gap-2">
            {TEMPLATES.map((tpl) => {
              const active = activeTemplate === tpl.id;
              return (
                <button
                  key={tpl.id}
                  type="button"
                  onClick={() => handleApplyTemplate(tpl.id)}
                  title={tpl.description}
                  className="group relative px-3 py-2 text-[11px] font-bold uppercase tracking-wider border transition-all"
                  style={{
                    background: active
                      ? "var(--accent-primary)"
                      : "var(--bg-secondary)",
                    color: active ? "white" : "var(--text-secondary)",
                    borderColor: active
                      ? "var(--accent-primary)"
                      : "var(--border-subtle)",
                    clipPath:
                      "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))",
                  }}
                  data-testid={`template-chip-${tpl.id}`}
                >
                  {tpl.label}
                </button>
              );
            })}
          </div>
          {activeTemplate && (
            <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {findTemplate(activeTemplate)?.description}
            </p>
          )}
        </GlassPanel>

        {/* ---- Two-column layout: condition builder + results ---- */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mt-6">
          {/* LEFT: condition builder */}
          <div className="lg:col-span-5 space-y-4">
            <GlassPanel title="SIGNAL CONDITIONS">
              <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                Enable indicators & set thresholds
              </h4>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {INDICATOR_ORDER.map((key) => {
                  const entry = form[key];
                  const sharedToggle = (enabled: boolean) =>
                    updateEntry(key, { enabled });
                  return (
                    <IndicatorCard
                      key={key}
                      indicator={key}
                      enabled={entry.enabled}
                      onToggle={sharedToggle}
                    >
                      {key === "rsi" && (
                        <RsiInputs
                          value={entry.rsi}
                          onChange={(v) => updateEntry("rsi", { rsi: v })}
                          disabled={!entry.enabled}
                        />
                      )}
                      {key === "macd" && (
                        <MacdInputs
                          value={entry.macd}
                          onChange={(v) => updateEntry("macd", { macd: v })}
                          disabled={!entry.enabled}
                        />
                      )}
                      {key === "bollinger" && (
                        <BollingerInputs
                          value={entry.bollinger}
                          onChange={(v) =>
                            updateEntry("bollinger", { bollinger: v })
                          }
                          disabled={!entry.enabled}
                        />
                      )}
                      {key === "kd" && (
                        <KdInputs
                          value={entry.kd}
                          onChange={(v) => updateEntry("kd", { kd: v })}
                          disabled={!entry.enabled}
                        />
                      )}
                      {key === "sma_cross" && (
                        <SmaCrossInputs
                          value={entry.sma_cross}
                          onChange={(v) =>
                            updateEntry("sma_cross", { sma_cross: v })
                          }
                          disabled={!entry.enabled}
                        />
                      )}
                      {key === "volume" && (
                        <VolumeInputs
                          value={entry.volume}
                          onChange={(v) => updateEntry("volume", { volume: v })}
                          disabled={!entry.enabled}
                        />
                      )}
                    </IndicatorCard>
                  );
                })}
              </div>

              <div className="mt-5 pt-4 border-t border-[var(--border-subtle)] space-y-3">
                <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  {enabledCount} 個指標啟用 · 將送出 {enabledKeys.length} 個後端策略
                </p>
                <ClippedButton
                  variant="red-solid"
                  size="md"
                  onClick={handleScan}
                  disabled={runScan.isPending}
                  className="w-full"
                >
                  {runScan.isPending
                    ? "INITIALIZING SCAN..."
                    : "RUN FULL MARKET SCAN"}
                </ClippedButton>
                {enabledKeys.length === 0 && enabledCount > 0 && (
                  <p className="text-[10px] text-[var(--stock-up)]/80 font-bold">
                    啟用的指標目前都沒有對應的後端策略，掃描會跑全部預設策略。
                  </p>
                )}
              </div>
            </GlassPanel>
          </div>

          {/* RIGHT: results */}
          <div className="lg:col-span-7">
            <GlassPanel
              title={
                scanResult
                  ? `SCAN RESULTS [${stocks.length}]`
                  : "ENGINE STANDBY"
              }
              noPadding
            >
              <div className="min-h-[600px] flex flex-col">
                {runScan.isPending ? (
                  <div className="flex-1 flex items-center justify-center">
                    <LoadingSpinner />
                  </div>
                ) : runScan.isError ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                    <p className="text-red-400 font-bold text-sm mb-4 uppercase tracking-widest">
                      {runScan.error instanceof Error
                        ? runScan.error.message
                        : "SCAN FAILURE"}
                    </p>
                    <ClippedButton
                      variant="red-ghost"
                      size="sm"
                      onClick={handleScan}
                    >
                      RETRY SCAN
                    </ClippedButton>
                  </div>
                ) : !scanResult ? (
                  <div className="flex-1 flex flex-col items-center justify-center p-12 text-center opacity-30">
                    <div className="w-16 h-16 mb-4 border-2 border-dashed border-[var(--text-muted)] rounded-full flex items-center justify-center">
                      <svg
                        className="w-8 h-8"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                        />
                      </svg>
                    </div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em]">
                      Ready for analysis
                    </p>
                  </div>
                ) : (
                  <div className="p-4">
                    <div className="flex items-center justify-end mb-4">
                      <button
                        onClick={() => {
                          const csvData = stocks.map((s) => ({
                            股票代號: s.symbol,
                            股票名稱: s.name,
                            綜合訊號: s.compositeAction,
                            分數: s.score,
                            ...Object.fromEntries(
                              s.signals.map((sig) => [
                                `${sig.strategy}_訊號`,
                                sig.action,
                              ]),
                            ),
                          }));
                          downloadCSV(
                            csvData,
                            `scanner_${new Date().toISOString().slice(0, 10)}.csv`,
                          );
                        }}
                        className="text-[10px] font-bold px-3 py-1 bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] transition-colors"
                      >
                        EXPORT CSV
                      </button>
                    </div>
                    <SignalTable
                      stocks={stocks}
                      actionFilter={actionFilter}
                      onActionFilterChange={setActionFilter}
                    />
                  </div>
                )}
              </div>
            </GlassPanel>
          </div>
        </div>
        </>
        )}
      </main>
    </div>
  );
}
