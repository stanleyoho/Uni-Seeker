"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useFinancialAnalysis, usePrices } from "@/hooks/use-market-data";
import { ChangeBadge, Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";

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
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-3 min-w-[260px]">
        <LoadingSpinner size="sm" />
      </div>
    );
  }

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-3 min-w-[260px] relative hover:bg-[var(--card-hover)] transition-colors duration-150">
      <button
        onClick={onRemove}
        className="absolute top-2 right-2 text-[var(--text-muted)] hover:text-red-400 transition-colors p-0.5"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Header */}
      <div className="mb-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-white font-bold text-sm">{symbol}</span>
          {price && (
            <ChangeBadge
              change={parseFloat(price.change)}
              changePct={price.change_percent}
            />
          )}
        </div>
        {price && (
          <span className="text-xl font-bold text-white mono-nums">
            {parseFloat(price.close).toLocaleString()}
          </span>
        )}
      </div>

      {/* Health Score */}
      {score && (
        <div className="mb-2 bg-[var(--bg-secondary)] rounded-lg p-2.5 border border-[var(--border-subtle)]">
          <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">{t.financial?.healthScore ?? "Health Score"}</div>
          <div className="flex items-center gap-1.5">
            <span className={`text-xl font-bold mono-nums ${score.total_score > 70 ? "text-[var(--score-excellent)] glow-green" : score.total_score >= 40 ? "text-[var(--score-good)] glow-amber" : "text-[var(--score-poor)] glow-red"}`}>
              {Math.round(score.total_score)}
            </span>
            <span className="text-[var(--text-muted)] text-[10px] mono-nums">/ 100</span>
          </div>
          <div className="grid grid-cols-2 gap-0.5 mt-1.5 text-[10px]">
            <div><span className="text-[var(--text-muted)]">{t.financial?.profitability ?? "Profit"}</span> <span className="text-white mono-nums ml-0.5">{score.profitability_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-muted)]">{t.financial?.efficiency ?? "Efficiency"}</span> <span className="text-white mono-nums ml-0.5">{score.efficiency_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-muted)]">{t.financial?.leverage ?? "Leverage"}</span> <span className="text-white mono-nums ml-0.5">{score.leverage_score.toFixed(0)}</span></div>
            <div><span className="text-[var(--text-muted)]">{t.financial?.growth ?? "Growth"}</span> <span className="text-white mono-nums ml-0.5">{score.growth_score.toFixed(0)}</span></div>
          </div>
        </div>
      )}

      {/* Key Ratios */}
      {ratios && (
        <div className="space-y-1 text-[10px]">
          {[
            { label: t.financial?.grossMargin ?? "Gross Margin", value: ratios.gross_margin, isPct: true },
            { label: t.financial?.netMargin ?? "Net Margin", value: ratios.net_margin, isPct: true },
            { label: t.financial?.roe ?? "ROE", value: ratios.roe, isPct: true },
            { label: t.financial?.debtRatio ?? "Debt Ratio", value: ratios.debt_ratio, isPct: false },
            { label: t.financial?.revenueGrowth ?? "Rev Growth", value: ratios.revenue_growth, isPct: true },
          ].map((item) => (
            <div key={item.label} className="flex items-center justify-between">
              <span className="text-[var(--text-muted)]">{item.label}</span>
              <span className={`mono-nums ${
                item.value != null && item.value > 0 ? "text-[var(--stock-down)] glow-green" :
                item.value != null && item.value < 0 ? "text-[var(--stock-up)] glow-red" : "text-white"
              }`}>
                {item.value != null ? (item.isPct ? `${(item.value * 100).toFixed(1)}%` : item.value.toFixed(2)) : "-"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      <div className="mb-4">
        <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">
          {cmp?.title ?? "Stock Comparison"}
        </h1>
        <p className="text-[var(--text-muted)] text-xs mt-0.5">
          {cmp?.subtitle ?? "Compare up to 5 stocks side by side"}
        </p>
      </div>

      {/* Add stock input */}
      <div className="relative mb-4 max-w-sm">
        <div className="flex gap-1.5">
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
            className="flex-1 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-white text-xs placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] transition-all"
          />
          <button
            onClick={() => addSymbol(input)}
            disabled={!input.trim() || symbols.length >= 5}
            className="px-3 py-2 bg-[var(--accent-blue)] text-white rounded-lg hover:bg-[var(--accent-blue-hover)] disabled:opacity-50 transition-all text-xs font-medium"
          >
            {cmp?.add ?? "Add"}
          </button>
        </div>

        {/* Suggestions dropdown */}
        {suggestions.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-lg shadow-xl z-30 overflow-hidden">
            {suggestions.map((s) => (
              <button
                key={s.symbol}
                onClick={() => addSymbol(s.symbol)}
                className="w-full px-3 py-2 text-left text-xs hover:bg-[var(--card-hover)] transition-colors flex items-center gap-2"
              >
                <span className="text-white mono-nums font-semibold">{s.symbol}</span>
                <span className="text-[var(--text-muted)]">{s.name}</span>
              </button>
            ))}
          </div>
        )}

        {symbols.length > 0 && (
          <div className="flex gap-1.5 mt-1.5 flex-wrap">
            {symbols.map((s) => (
              <Badge key={s} variant="blue" className="gap-1">
                {s}
                <button onClick={() => removeSymbol(s)} className="hover:text-red-400 ml-0.5">x</button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Comparison cards */}
      {symbols.length === 0 ? (
        <EmptyState
          title={cmp?.emptyTitle ?? "Add stocks to compare"}
          message={cmp?.emptyMessage ?? "Enter stock symbols above to compare financial metrics side by side"}
        />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-3">
          {symbols.map((sym) => (
            <CompareStock key={sym} symbol={sym} onRemove={() => removeSymbol(sym)} />
          ))}
        </div>
      )}
    </div>
  );
}
