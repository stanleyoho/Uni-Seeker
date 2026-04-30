"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useFinancialAnalysis, usePrices } from "@/hooks/use-market-data";
import { ChangeBadge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";

/* ------------------------------------------------------------------ */
/*  CompareStock card                                                  */
/* ------------------------------------------------------------------ */

function CompareStock({ symbol, onRemove }: { symbol: string; onRemove: () => void }) {
  const { t } = useI18n();
  const { data: priceData, isLoading: priceLoading } = usePrices(symbol, 1);
  const { data: financials, isLoading: finLoading } = useFinancialAnalysis(symbol);

  const price = priceData?.data?.[0];
  const score = financials?.health_scores?.[0];
  const ratios = financials?.ratios?.[0];
  const loading = priceLoading || finLoading;

  if (loading) {
    return (
      <GlassPanel className="min-w-0 md:min-w-[280px] w-full">
        <div className="flex items-center justify-center py-8">
          <LoadingSpinner size="sm" />
        </div>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="min-w-0 md:min-w-[280px] w-full relative group">
      {/* Remove button */}
      <button
        onClick={onRemove}
        className="absolute top-3 right-3 text-[var(--text-secondary)] hover:text-red-400 transition-colors p-1 opacity-60 group-hover:opacity-100"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Header */}
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[var(--foreground)] font-bold text-sm tracking-tight">{symbol}</span>
          {price && (
            <ChangeBadge
              change={parseFloat(price.change)}
              changePct={price.change_percent}
            />
          )}
        </div>
        {price && (
          <span className="text-2xl font-bold text-[var(--foreground)] mono-nums">
            {parseFloat(price.close).toLocaleString()}
          </span>
        )}
      </div>

      {/* Health Score */}
      {score && (
        <div className="mb-3 rounded-lg p-3" style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)" }}>
          <div className="text-[10px] text-[var(--text-secondary)] uppercase tracking-wider mb-1 font-semibold">
            {t.financial?.healthScore ?? "Health Score"}
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`text-xl font-bold mono-nums ${score.total_score > 70 ? "text-[var(--score-excellent)] glow-green" : score.total_score >= 40 ? "text-[var(--score-good)] glow-amber" : "text-[var(--score-poor)] glow-red"}`}>
              {Math.round(score.total_score)}
            </span>
            <span className="text-[var(--text-secondary)] text-[10px] mono-nums">/ 100</span>
          </div>
          <div className="grid grid-cols-2 gap-1 mt-2 text-[10px]">
            <div><span className="text-[var(--text-secondary)]">{t.financial?.profitability ?? "Profit"}</span> <span className="text-[var(--foreground)] mono-nums ml-0.5">{score.profitability_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-secondary)]">{t.financial?.efficiency ?? "Efficiency"}</span> <span className="text-[var(--foreground)] mono-nums ml-0.5">{score.efficiency_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-secondary)]">{t.financial?.leverage ?? "Leverage"}</span> <span className="text-[var(--foreground)] mono-nums ml-0.5">{score.leverage_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-secondary)]">{t.financial?.growth ?? "Growth"}</span> <span className="text-[var(--foreground)] mono-nums ml-0.5">{score.growth_score.toFixed(0)}</span></div>
          </div>
        </div>
      )}

      {/* Key Ratios - table with hover rows */}
      {ratios && (
        <div className="space-y-0">
          {[
            { label: t.financial?.grossMargin ?? "Gross Margin", value: ratios.gross_margin, isPct: true },
            { label: t.financial?.netMargin ?? "Net Margin", value: ratios.net_margin, isPct: true },
            { label: t.financial?.roe ?? "ROE", value: ratios.roe, isPct: true },
            { label: t.financial?.debtRatio ?? "Debt Ratio", value: ratios.debt_ratio, isPct: false },
            { label: t.financial?.revenueGrowth ?? "Rev Growth", value: ratios.revenue_growth, isPct: true },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-[var(--bg-secondary)] transition-colors text-[11px]"
            >
              <span className="text-[var(--text-secondary)]">{item.label}</span>
              <span className={`mono-nums font-medium ${
                item.value != null && item.value > 0 ? "text-[var(--stock-down)] glow-green" :
                item.value != null && item.value < 0 ? "text-[var(--stock-up)] glow-red" : "text-[var(--foreground)]"
              }`}>
                {item.value != null ? (item.isPct ? `${(item.value * 100).toFixed(1)}%` : item.value.toFixed(2)) : "-"}
              </span>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  ComparePage                                                        */
/* ------------------------------------------------------------------ */

export default function ComparePage() {
  const { t } = useI18n();
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

  const cmp = t.compare;

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Page header */}
      <div className="mb-5">
        <h1 className="text-xl md:text-2xl font-bold text-[var(--foreground)] tracking-tight">
          {cmp?.title ?? "Stock Comparison"}
        </h1>
        <p className="text-[var(--text-secondary)] text-xs mt-1">
          {cmp?.subtitle ?? "Compare up to 5 stocks side by side"}
        </p>
      </div>

      {/* Add stock input */}
      <div className="relative mb-5 max-w-md">
        <div className="flex gap-2 items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && input.trim()) {
                addSymbol(input);
              }
            }}
            placeholder={cmp?.addPlaceholder ?? "Add stock (e.g. 2330.TW, AAPL)"}
            className="flex-1 px-3 py-2 text-xs text-[var(--foreground)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] transition-all"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: 0,
            }}
          />
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => addSymbol(input)}
            disabled={!input.trim() || symbols.length >= 5}
          >
            {cmp?.add ?? "加入"}
          </ClippedButton>
        </div>

        {/* Suggestions dropdown */}
        {suggestions.length > 0 && (
          <div
            className="absolute top-full left-0 right-0 mt-1 shadow-xl z-30 overflow-hidden"
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
            }}
          >
            {suggestions.map((s) => (
              <button
                key={s.symbol}
                onClick={() => addSymbol(s.symbol)}
                className="w-full px-3 py-2 text-left text-xs hover:bg-[var(--glass-bg)] transition-colors flex items-center gap-2"
              >
                <span className="text-[var(--foreground)] mono-nums font-semibold">{s.symbol}</span>
                <span className="text-[var(--text-secondary)]">{s.name}</span>
              </button>
            ))}
          </div>
        )}

        {/* Selected symbols tags */}
        {symbols.length > 0 && (
          <div className="flex gap-2 mt-2 flex-wrap">
            {symbols.map((s) => (
              <span
                key={s}
                className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold mono-nums"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-color)",
                  color: "var(--foreground)",
                }}
              >
                {s}
                <button onClick={() => removeSymbol(s)} className="hover:text-red-400 ml-0.5 text-[var(--text-secondary)]">
                  x
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Comparison cards grid */}
      {symbols.length === 0 ? (
        <GlassPanel>
          <EmptyState
            title={cmp?.emptyTitle ?? "Add stocks to compare"}
            message={cmp?.emptyMessage ?? "Enter stock symbols above to compare financial metrics side by side"}
          />
        </GlassPanel>
      ) : (
        <div
          className="grid gap-4 pb-4"
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          }}
        >
          {symbols.map((sym) => (
            <CompareStock key={sym} symbol={sym} onRemove={() => removeSymbol(sym)} />
          ))}
        </div>
      )}
    </div>
  );
}
