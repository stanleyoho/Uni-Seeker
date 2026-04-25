"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const { t } = useI18n();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [loading, setLoading] = useState(false);

  // Reset state when opening
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setSelectedIndex(-1);
      setLoading(false);
      // Auto-focus after the modal renders
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      const data = await searchStocks(query, 10);
      setResults(data);
      setSelectedIndex(-1);
      setLoading(false);
    }, 200);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIndex < 0 || !listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-result-item]");
    items[selectedIndex]?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const navigateToStock = useCallback(
    (symbol: string) => {
      onClose();
      router.push(`/stocks/${encodeURIComponent(symbol)}`);
    },
    [onClose, router],
  );

  const marketLabel = (market: string) => {
    if (market.startsWith("TW_TWSE")) return t.search.listed;
    if (market.startsWith("TW_TPEX")) return t.search.otc;
    if (market.includes("NASDAQ")) return "NASDAQ";
    if (market.includes("NYSE")) return "NYSE";
    return market;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev < results.length - 1 ? prev + 1 : 0,
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev > 0 ? prev - 1 : results.length - 1,
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIndex >= 0 && results[selectedIndex]) {
        navigateToStock(results[selectedIndex].symbol);
      } else if (query.trim()) {
        navigateToStock(query.trim().toUpperCase());
      }
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Search stocks"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative w-full max-w-lg mx-4 bg-[#0a0a0b] border border-[var(--border-color)] rounded-xl shadow-2xl shadow-black/80 overflow-hidden animate-slide-down">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-color)]">
          <svg
            className="w-4 h-4 text-[var(--text-muted)] shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t.search.placeholder}
            className="flex-1 bg-transparent text-white text-sm placeholder-[var(--text-muted)] outline-none mono-nums"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="hidden sm:inline-flex items-center justify-center text-[10px] text-[var(--text-muted)] border border-[var(--border-color)] rounded px-1.5 py-0.5 font-mono leading-none">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          className="max-h-[320px] overflow-y-auto overscroll-contain"
          role="listbox"
        >
          {loading && query.trim() && (
            <div className="px-4 py-6 text-center text-[var(--text-muted)] text-xs">
              {t.stock?.loading || "Loading..."}
            </div>
          )}

          {!loading && query.trim() && results.length === 0 && (
            <div className="px-4 py-6 text-center text-[var(--text-muted)] text-xs">
              {t.search.noResults}
            </div>
          )}

          {results.map((stock, index) => (
            <button
              key={stock.symbol}
              data-result-item
              type="button"
              role="option"
              aria-selected={index === selectedIndex}
              onClick={() => navigateToStock(stock.symbol)}
              className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors duration-75 ${
                index === selectedIndex
                  ? "bg-[var(--card-active)]"
                  : "hover:bg-[var(--card-hover)]"
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="text-white font-semibold text-xs mono-nums bg-[var(--card-active)] px-1.5 py-0.5 rounded shrink-0">
                  {stock.symbol.replace(".TW", "").replace(".TWO", "")}
                </span>
                <span className="text-[var(--text-secondary)] text-xs truncate">
                  {stock.name}
                </span>
              </div>
              <span className="text-[10px] text-[var(--text-muted)] px-1.5 py-0.5 border border-[var(--border-color)] rounded shrink-0 ml-2">
                {marketLabel(stock.market)}
              </span>
            </button>
          ))}
        </div>

        {/* Footer hint */}
        {results.length > 0 && (
          <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--border-color)] text-[10px] text-[var(--text-muted)]">
            <span className="flex items-center gap-1">
              <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">&uarr;&darr;</kbd>
              navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">&crarr;</kbd>
              select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">esc</kbd>
              close
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
