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
      <GlassPanel className="flex-1 min-w-[240px]">
        <div className="flex items-center justify-center py-6">
          <LoadingSpinner size="sm" />
        </div>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="flex-1 min-w-[240px] relative group">
      {/* Remove button */}
      <button
        onClick={onRemove}
        className="absolute top-2 right-2 text-[var(--text-muted)] hover:text-red-400 transition-colors p-0.5 opacity-0 group-hover:opacity-100"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
          <span className="text-xl font-bold text-[var(--foreground)] mono-nums">
            {parseFloat(price.close).toLocaleString()}
          </span>
        )}
      </div>

      {/* Health Score - compact */}
      {score && (
        <div
          className="mb-3 p-2.5"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)" }}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-semibold">
              {t.financial?.healthScore ?? "Health"}
            </span>
            <div className="flex items-baseline gap-1">
              <span className={`text-lg font-bold mono-nums ${score.total_score > 70 ? "text-[var(--score-excellent)] glow-green" : score.total_score >= 40 ? "text-[var(--score-good)] glow-amber" : "text-[var(--score-poor)] glow-red"}`}>
                {Math.round(score.total_score)}
              </span>
              <span className="text-[var(--text-muted)] text-[10px]">/ 100</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>{t.financial?.profitability ?? "Profit"}</span>
              <span className="mono-nums" style={{ color: "var(--foreground)" }}>{score.profitability_score.toFixed(0)}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>{t.financial?.efficiency ?? "Efficiency"}</span>
              <span className="mono-nums" style={{ color: "var(--foreground)" }}>{score.efficiency_score.toFixed(0)}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>{t.financial?.leverage ?? "Leverage"}</span>
              <span className="mono-nums" style={{ color: "var(--foreground)" }}>{score.leverage_score.toFixed(0)}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>{t.financial?.growth ?? "Growth"}</span>
              <span className="mono-nums" style={{ color: "var(--foreground)" }}>{score.growth_score.toFixed(0)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Key Ratios - dense rows */}
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
              className="flex items-center justify-between px-1.5 py-1 text-[11px] transition-colors hover:bg-[var(--card-hover)]"
            >
              <span style={{ color: "var(--text-secondary)" }}>{item.label}</span>
              <span className={`mono-nums font-medium ${
                item.value != null && item.value > 0 ? "text-[var(--stock-down)]" :
                item.value != null && item.value < 0 ? "text-[var(--stock-up)]" : "text-[var(--foreground)]"
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
      {/* Top: search input + selected tags inline */}
      <div className="relative mb-4">
        <div className="flex gap-2 items-center flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
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
              className="w-full px-3 py-2 text-xs text-[var(--foreground)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] transition-all"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 0,
              }}
            />
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
                    className="w-full px-3 py-1.5 text-left text-xs hover:bg-[var(--card-hover)] transition-colors flex items-center gap-2"
                  >
                    <span className="text-[var(--foreground)] mono-nums font-semibold">{s.symbol}</span>
                    <span className="text-[var(--text-secondary)]">{s.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => addSymbol(input)}
            disabled={!input.trim() || symbols.length >= 5}
          >
            {cmp?.add ?? "加入"}
          </ClippedButton>

          {/* Selected symbols as inline tags */}
          {symbols.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 px-2 py-1.5 text-[11px] font-semibold mono-nums"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                color: "var(--foreground)",
              }}
            >
              {s}
              <button
                onClick={() => removeSymbol(s)}
                className="hover:text-red-400 ml-0.5 text-[var(--text-muted)]"
              >
                x
              </button>
            </span>
          ))}

          {symbols.length > 0 && (
            <span className="text-[10px] text-[var(--text-muted)]">
              {symbols.length}/5
            </span>
          )}
        </div>
      </div>

      {/* Horizontal card grid */}
      {symbols.length === 0 ? (
        <GlassPanel>
          <EmptyState
            title={cmp?.emptyTitle ?? "Add stocks to compare"}
            message={cmp?.emptyMessage ?? "Enter stock symbols above to compare financial metrics side by side"}
          />
        </GlassPanel>
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-2">
          {symbols.map((sym) => (
            <CompareStock key={sym} symbol={sym} onRemove={() => removeSymbol(sym)} />
          ))}
        </div>
      )}
    </div>
  );
}
