"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

export default function HomePage() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<StockSearchResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const router = useRouter();
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (query.trim().length === 0) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      const results = await searchStocks(query, 8);
      setSuggestions(results);
      setShowDropdown(results.length > 0);
      setSelectedIndex(-1);
    }, 200);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const navigateToStock = (symbol: string) => {
    setShowDropdown(false);
    setQuery(symbol);
    router.push(`/stocks/${encodeURIComponent(symbol)}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIndex >= 0 && suggestions[selectedIndex]) {
      navigateToStock(suggestions[selectedIndex].symbol);
    } else if (query.trim()) {
      navigateToStock(query.trim().toUpperCase());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown || suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  const marketLabel = (market: string) => {
    if (market.startsWith("TW_TWSE")) return t.search.listed;
    if (market.startsWith("TW_TPEX")) return t.search.otc;
    if (market.includes("NASDAQ")) return "NASDAQ";
    if (market.includes("NYSE")) return "NYSE";
    return market;
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/5 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-600/5 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 flex flex-col items-center w-full">
        {/* Hero */}
        <h1 className="text-5xl md:text-6xl font-bold mb-3 gradient-text tracking-tight">
          {t.app.title}
        </h1>
        <p className="text-[#94a3b8] mb-10 text-lg">{t.app.subtitle}</p>

        {/* Search */}
        <div ref={dropdownRef} className="relative w-full max-w-lg">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <div className="relative flex-1">
              <svg
                className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748b]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
                placeholder={t.search.placeholder}
                className="w-full pl-10 pr-4 py-3 rounded-xl bg-[#1a2332] border border-[#1e293b] text-white placeholder-[#64748b] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
                autoComplete="off"
              />
            </div>
            <button
              type="submit"
              className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all duration-200 font-medium shadow-lg shadow-blue-600/20 hover:shadow-blue-600/30"
            >
              {t.search.button}
            </button>
          </form>

          {showDropdown && suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-2 bg-[#1a2332] border border-[#1e293b] rounded-xl shadow-2xl shadow-black/40 z-50 overflow-hidden animate-slide-down">
              {suggestions.map((stock, index) => (
                <button
                  key={stock.symbol}
                  type="button"
                  onClick={() => navigateToStock(stock.symbol)}
                  className={`w-full px-4 py-3 flex items-center justify-between text-left transition-all duration-150 ${
                    index === selectedIndex
                      ? "bg-[#253449]"
                      : "hover:bg-[#1e293b]"
                  } ${index > 0 ? "border-t border-[#1e293b]/50" : ""}`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-white font-mono font-semibold text-sm bg-[#253449] px-2 py-0.5 rounded">
                      {stock.symbol.replace(".TW", "").replace(".TWO", "")}
                    </span>
                    <span className="text-[#94a3b8] text-sm">{stock.name}</span>
                  </div>
                  <span className="text-xs text-[#64748b] px-2 py-0.5 border border-[#1e293b] rounded-md">
                    {marketLabel(stock.market)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Quick stats */}
        <div className="mt-16 flex items-center gap-6 text-[#64748b] text-sm">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span>TW + US Markets</span>
          </div>
          <div className="w-px h-4 bg-[#1e293b]" />
          <span>15+ Indicators</span>
          <div className="w-px h-4 bg-[#1e293b]" />
          <span>Real-time Analysis</span>
        </div>
      </div>
    </div>
  );
}
