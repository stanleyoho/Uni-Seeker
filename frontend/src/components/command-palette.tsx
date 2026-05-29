"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { QuoteRow } from "@/components/quote-row";

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

  // Reset state when opening. The sync setState calls below are
  // intentional and correct: opening the palette is a parent-driven
  // event (via the `open` prop transition false->true) that must wipe
  // any leftover query/results from a prior open. Restructuring as
  // derived state would require unmount/remount on every open, which
  // throws away the inputRef focus that requestAnimationFrame relies on.
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset modal-local state on parent-driven open transition; remount alternative breaks focus management
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

  // Debounced search. The empty-query branch clears results sync; the
  // non-empty branch flips loading=true sync, then setState in the
  // setTimeout callback (which the rule allows). Both sync paths
  // legitimately mirror the user's `query` input, but there is no
  // clean derive-during-render alternative because (a) results have to
  // be real state to survive across the debounced async callback, and
  // (b) loading must flip at the moment the debounce window opens, not
  // at the moment results arrive.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!query.trim()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear results when user empties the input; results must remain real state for the async setTimeout path
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
    }, 300);

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
        className="absolute inset-0 backdrop-blur-[8px]"
        style={{ background: "rgba(0,0,0,0.7)" }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className="relative w-full max-w-lg mx-4 border rounded-xl overflow-hidden animate-slide-down"
        style={{
          background: "var(--glass-bg)",
          borderColor: "var(--border-color)",
          boxShadow: "var(--glass-shadow)",
        }}
      >
        {/* Search input */}
        <div
          className="flex items-center gap-3 px-4 py-3"
          style={{
            background: "var(--bg-secondary)",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
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
            className="flex-1 bg-transparent text-[var(--foreground)] text-sm placeholder-[var(--text-muted)] outline-none mono-nums"
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
            // QuoteRow is the canonical stock-listing row. StockSearchResult
            // currently only ships symbol/name/market — price + change get
            // rendered as em-dashes (flagged backend gap in the PR body).
            // The aria-selected + data-result-item passthroughs preserve
            // the existing listbox keyboard nav.
            <QuoteRow
              key={stock.symbol}
              symbol={stock.symbol}
              name={stock.name}
              market={marketLabel(stock.market)}
              onClick={() => navigateToStock(stock.symbol)}
              role="option"
              ariaSelected={index === selectedIndex}
              dataAttributes={{ "data-result-item": true }}
              className={
                index === selectedIndex
                  ? "bg-[var(--card-active)]"
                  : "hover:bg-[var(--card-hover)]"
              }
              style={
                index === selectedIndex
                  ? { borderLeft: "2px solid var(--accent-primary)" }
                  : undefined
              }
            />
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
