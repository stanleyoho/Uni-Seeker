"use client";

// ---------------------------------------------------------------------------
// CompareTabPanel — extracted from the former `/research/compare` route.
//
// As of the route-consolidation refactor, `/research/compare` is now a
// permanent redirect (`./compare/page.tsx`) that lands on
// `/research?tab=compare`, where the parent `/research` page mounts this
// panel. The visual + state behaviour is unchanged — it's a pure relocation
// so the comparison flow lives inside the single Research surface alongside
// the Scan + Low-Base tabs, instead of taking up a sibling route slot.
//
// The AmbientBackground that used to live in this file was dropped because
// the parent `/research/page.tsx` already mounts one. Stacking two ambient
// layers would compound the glass-blur cost without changing the visual
// result.
// ---------------------------------------------------------------------------

import { useState } from "react";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useFinancialAnalysis, usePrices } from "@/hooks/use-market-data";
import { LoadingSpinner } from "@/components/ui/loading";
import { GlassPanel } from "@/components/stratos/primitives";

/* ------------------------------------------------------------------ */
/*  CompareStock card                                                  */
/* ------------------------------------------------------------------ */

function CompareStock({ symbol, onRemove }: { symbol: string; onRemove: () => void }) {
  const { data: priceData, isLoading: priceLoading } = usePrices(symbol, 1);
  const { data: financials, isLoading: finLoading } = useFinancialAnalysis(symbol);

  const price = priceData?.data?.[0];
  const score = financials?.health_scores?.[0];
  const ratios = financials?.ratios?.[0];
  const loading = priceLoading || finLoading;

  if (loading) {
    return (
      <GlassPanel className="flex-1 min-w-[280px]">
        <div className="flex items-center justify-center py-20">
          <LoadingSpinner size="sm" />
        </div>
      </GlassPanel>
    );
  }

  const isUp = price ? parseFloat(price.change) >= 0 : true;
  const totalScore = score ? parseFloat(score.total_score) : 0;
  const profitabilityScore = score ? parseFloat(score.profitability_score) : 0;
  const growthScore = score ? parseFloat(score.growth_score) : 0;
  const leverageScore = score ? parseFloat(score.leverage_score) : 0;
  const efficiencyScore = score ? parseFloat(score.efficiency_score) : 0;

  return (
    <GlassPanel className="flex-1 min-w-[280px] relative group border-t-2" style={{ borderTopColor: isUp ? "var(--stock-up)" : "var(--stock-down)" }}>
      {/* Remove button */}
      <button
        onClick={onRemove}
        className="absolute top-3 right-3 text-[var(--text-muted)] hover:text-red-500 transition-colors p-1 bg-[var(--card-hover)] border border-[var(--border-subtle)] opacity-0 group-hover:opacity-100"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xl font-bold text-[var(--foreground)] tracking-tighter">{symbol}</span>
          {price && (
            <span className={`text-[10px] font-bold px-1.5 py-0.5 ${isUp ? "bg-[var(--stock-up-bg)] text-[var(--stock-up)]" : "bg-[var(--stock-down-bg)] text-[var(--stock-down)]"}`}>
              {isUp ? "+" : ""}{parseFloat(price.change_percent).toFixed(2)}%
            </span>
          )}
        </div>
        {price && (
          <div className="text-2xl font-bold text-[var(--foreground)] tabular-nums">
            {parseFloat(price.close).toLocaleString()}
          </div>
        )}
      </div>

      {/* Health Score */}
      {score && (
        <div className="mb-6 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-[var(--text-muted)] uppercase font-bold tracking-widest">
              HEALTH INDEX
            </span>
            <div className="text-2xl font-bold tabular-nums" style={{ color: totalScore > 70 ? "var(--stock-up)" : "var(--foreground)" }}>
              {Math.round(totalScore)}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[10px] font-bold">
            <div className="flex justify-between border-b border-[var(--border-subtle)] pb-1">
              <span className="text-[var(--text-muted)]">PROFIT</span>
              <span className="tabular-nums">{profitabilityScore.toFixed(0)}</span>
            </div>
            <div className="flex justify-between border-b border-[var(--border-subtle)] pb-1">
              <span className="text-[var(--text-muted)]">GROWTH</span>
              <span className="tabular-nums">{growthScore.toFixed(0)}</span>
            </div>
            <div className="flex justify-between border-b border-[var(--border-subtle)] pb-1">
              <span className="text-[var(--text-muted)]">LEVERAGE</span>
              <span className="tabular-nums">{leverageScore.toFixed(0)}</span>
            </div>
            <div className="flex justify-between border-b border-[var(--border-subtle)] pb-1">
              <span className="text-[var(--text-muted)]">EFFICIENCY</span>
              <span className="tabular-nums">{efficiencyScore.toFixed(0)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Key Ratios */}
      {ratios && (
        <div className="space-y-1">
          <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-3">KEY PERFORMANCE</h4>
          {[
            { label: "GROSS MARGIN", value: ratios.gross_margin, isPct: true },
            { label: "NET MARGIN", value: ratios.net_margin, isPct: true },
            { label: "ROE", value: ratios.roe, isPct: true },
            { label: "DEBT RATIO", value: ratios.debt_ratio, isPct: false },
          ].map((item) => {
            const val = item.value != null ? parseFloat(item.value) : null;
            return (
              <div
                key={item.label}
                className="flex items-center justify-between px-3 py-2 text-[11px] font-bold bg-[var(--bg-secondary)]/30 border-b border-[var(--border-subtle)]"
              >
                <span className="text-[var(--text-secondary)]">{item.label}</span>
                <span className={`tabular-nums ${
                  val != null && val > 0 ? "text-[var(--stock-up)]" :
                  val != null && val < 0 ? "text-[var(--stock-down)]" : "text-[var(--foreground)]"
                }`}>
                  {val != null ? (item.isPct ? `${(val * 100).toFixed(1)}%` : val.toFixed(2)) : "-"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </GlassPanel>
  );
}

export function CompareTabPanel() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<StockSearchResult[]>([]);

  const addSymbol = (sym: string) => {
    const upper = sym.trim().toUpperCase();
    if (upper && !symbols.includes(upper) && symbols.length < 5) {
      setSymbols([...symbols, upper]);
      setInput("");
      setSuggestions([]);
    }
  };

  const removeSymbol = (sym: string) => {
    setSymbols(symbols.filter((s) => s !== sym));
  };

  const handleInputChange = async (value: string) => {
    setInput(value);
    if (value.trim().length >= 1) {
      const results = await searchStocks(value, 5);
      setSuggestions(results);
    } else {
      setSuggestions([]);
    }
  };

  // No AmbientBackground / outer wrapper here — the parent `/research`
  // page already mounts a single AmbientBackground and a `<main>` with
  // page padding around all three tab panels. Returning a fragment keeps
  // the layout identical to the legacy `/research/compare` route while
  // avoiding nested `<main>` semantics + duplicate ambient layers.
  return (
    <>
      {/* Search & Selection */}
        <div className="flex flex-col md:flex-row gap-4 mb-8 items-start">
          <div className="relative w-full max-w-md">
            <input
              type="text"
              value={input}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && input.trim()) addSymbol(input);
              }}
              placeholder="SEARCH ASSETS TO COMPARE..."
              className="w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm font-bold text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none transition-all"
            />
            {suggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 border border-[var(--border-subtle)] bg-[var(--bg-secondary)] z-50">
                {suggestions.map((s) => (
                  <button
                    key={s.symbol}
                    onClick={() => addSymbol(s.symbol)}
                    className="w-full px-4 py-2 text-left text-xs font-bold hover:bg-[var(--card-hover)] flex justify-between items-center"
                  >
                    <span className="text-[var(--foreground)]">{s.symbol}</span>
                    <span className="text-[var(--text-muted)]">{s.name.toUpperCase()}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            {symbols.map((s) => (
              <div
                key={s}
                className="flex items-center gap-2 px-3 py-1.5 bg-[var(--accent-primary)] text-white text-[10px] font-bold"
                style={{ clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))" }}
              >
                {s}
                <button onClick={() => removeSymbol(s)} className="hover:scale-110 transition-transform">
                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Comparison Grid */}
        {symbols.length === 0 ? (
          <GlassPanel className="py-24 text-center">
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">Asset comparison standby</p>
            <p className="text-[10px] text-[var(--text-muted)] mt-2 uppercase">ADD UP TO 5 SECURITIES TO BEGIN ANALYSIS</p>
          </GlassPanel>
        ) : (
          <div className="flex gap-6 overflow-x-auto pb-6 scrollbar-hide">
            {symbols.map((sym) => (
              <CompareStock key={sym} symbol={sym} onRemove={() => removeSymbol(sym)} />
            ))}
          </div>
        )}
    </>
  );
}

export default CompareTabPanel;
