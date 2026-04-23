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
    <div className="min-h-screen flex flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold mb-2">{t.app.title}</h1>
      <p className="text-gray-400 mb-8">{t.app.subtitle}</p>

      <div ref={dropdownRef} className="relative w-full max-w-md">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
            placeholder={t.search.placeholder}
            className="flex-1 px-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            autoComplete="off"
          />
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            {t.search.button}
          </button>
        </form>

        {showDropdown && suggestions.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
            {suggestions.map((stock, index) => (
              <button
                key={stock.symbol}
                type="button"
                onClick={() => navigateToStock(stock.symbol)}
                className={`w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-700 transition ${
                  index === selectedIndex ? "bg-gray-700" : ""
                }`}
              >
                <div>
                  <span className="text-white font-mono font-medium">
                    {stock.symbol.replace(".TW", "").replace(".TWO", "")}
                  </span>
                  <span className="text-gray-400 ml-2">{stock.name}</span>
                </div>
                <span className="text-xs text-gray-500 px-2 py-0.5 bg-gray-900 rounded">
                  {marketLabel(stock.market)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
