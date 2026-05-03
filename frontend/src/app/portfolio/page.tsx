"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { useWatchlist, type WatchlistItem } from "@/hooks/use-watchlist";
import { fetchPrices, type StockPrice } from "@/lib/api-client";
import { downloadCSV } from "@/lib/csv-export";
import { parseCSV } from "@/lib/csv-import";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { Sparkline } from "@/components/stratos/charts";
import { MarketBadge } from "@/components/ui/badge";

import { AmbientBackground } from "@/components/stratos/ambient";

interface WatchlistRowData extends WatchlistItem {
  price?: StockPrice | null;
  loading: boolean;
}

type SortKey = "symbol" | "name" | "change" | "volume";

export default function WatchlistPage() {
  const { t } = useI18n();
  const { items, add, remove, removeMany } = useWatchlist();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rowData, setRowData] = useState<WatchlistRowData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<SortKey>("symbol");

  const loadPrices = useCallback(async () => {
    setLoading(true);
    const rows: WatchlistRowData[] = items.map((item) => ({ ...item, loading: true }));
    setRowData(rows);

    const updated = await Promise.all(
      items.map(async (item) => {
        try {
          const res = await fetchPrices(item.symbol, 1);
          return { ...item, price: res.data[0] ?? null, loading: false };
        } catch {
          return { ...item, price: null, loading: false };
        }
      }),
    );
    setRowData(updated);
    setLoading(false);
  }, [items]);

  useEffect(() => {
    if (items.length > 0) {
      loadPrices();
    } else {
      setRowData([]);
      setLoading(false);
    }
  }, [items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clear selection for symbols that no longer exist
  useEffect(() => {
    const currentSymbols = new Set(items.map((i) => i.symbol));
    setSelected((prev) => {
      const next = new Set([...prev].filter((s) => currentSymbols.has(s)));
      if (next.size !== prev.size) return next;
      return prev;
    });
  }, [items]);

  const sortedRows = useMemo(() => {
    const rows = [...rowData];
    switch (sortBy) {
      case "symbol":
        rows.sort((a, b) => a.symbol.localeCompare(b.symbol));
        break;
      case "name":
        rows.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "change":
        rows.sort((a, b) => {
          const aChange = a.price ? parseFloat(a.price.change_percent) : 0;
          const bChange = b.price ? parseFloat(b.price.change_percent) : 0;
          return bChange - aChange;
        });
        break;
      case "volume":
        rows.sort((a, b) => {
          const aVol = a.price?.volume ?? 0;
          const bVol = b.price?.volume ?? 0;
          return bVol - aVol;
        });
        break;
    }
    return rows;
  }, [rowData, sortBy]);

  const allSelected = rowData.length > 0 && selected.size === rowData.length;
  const someSelected = selected.size > 0 && selected.size < rowData.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(rowData.map((r) => r.symbol)));
    }
  };

  const toggleSelect = (symbol: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      return next;
    });
  };

  const handleBulkRemove = () => {
    if (selected.size === 0) return;
    removeMany(selected);
    setSelected(new Set());
  };

  const handleExport = () => {
    const data = items.map((item) => ({
      symbol: item.symbol,
      name: item.name,
      added_date: item.addedAt.split("T")[0],
    }));
    downloadCSV(data, "watchlist.csv");
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result as string;
      const symbols = parseCSV(text);
      for (const symbol of symbols) {
        add(symbol, symbol, "");
      }
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const wl = t.watchlist;

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 border-b border-[var(--border-subtle)] pb-4 gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              {wl?.title || "Watchlist Management"}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {items.length} ACTIVE SECURITIES MONITORED
            </p>
          </div>
          
          <div className="flex flex-wrap gap-2">
            <label className="cursor-pointer">
              <button 
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-1.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:border-[var(--accent-cyan)] transition-all"
              >
                IMPORT CSV
              </button>
              <input ref={fileInputRef} type="file" accept=".csv" onChange={handleImport} className="hidden" />
            </label>
            <button 
              onClick={handleExport}
              className="px-4 py-1.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:border-[var(--accent-cyan)] transition-all"
            >
              EXPORT CSV
            </button>
            <ClippedButton variant="red-solid" size="sm" onClick={loadPrices} disabled={loading}>
              {loading ? "FETCHING..." : "SYNC PRICES"}
            </ClippedButton>
            {selected.size > 0 && (
              <ClippedButton variant="red-ghost" size="sm" onClick={handleBulkRemove}>
                DELETE SELECTED [{selected.size}]
              </ClippedButton>
            )}
          </div>
        </div>

        {/* List Content */}
        {items.length === 0 ? (
          <GlassPanel className="py-24 text-center">
            <div className="w-16 h-16 mx-auto mb-6 flex items-center justify-center bg-[var(--bg-secondary)] border border-dashed border-[var(--border-subtle)] rotate-45">
              <svg className="-rotate-45 w-6 h-6 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">Asset monitoring offline</p>
            <p className="text-[10px] text-[var(--text-muted)] mt-2 uppercase">Your watchlist is currently empty</p>
            <Link href="/" className="inline-block mt-6">
              <ClippedButton variant="red-solid" size="md">DISCOVER ASSETS</ClippedButton>
            </Link>
          </GlassPanel>
        ) : (
          <GlassPanel noPadding title="REAL-TIME ASSET MONITOR">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                    <th className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => { if (el) el.indeterminate = someSelected; }}
                        onChange={toggleSelectAll}
                        className="w-3.5 h-3.5 accent-[var(--accent-primary)] cursor-pointer"
                      />
                    </th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Symbol</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Name</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right hidden sm:table-cell">Intraday</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Price</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Chg%</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right hidden md:table-cell">Market Cap</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right w-24">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {sortedRows.map((row) => {
                    const price = row.price;
                    const changePct = price ? parseFloat(price.change_percent) : 0;
                    const isUp = changePct >= 0;
                    const isSelected = selected.has(row.symbol);

                    return (
                      <tr 
                        key={row.symbol}
                        className={`transition-all hover:bg-[var(--card-hover)] group relative ${isSelected ? "bg-[var(--accent-primary)]/5" : ""}`}
                      >
                        <td className="px-4 py-4">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(row.symbol)}
                            className="w-3.5 h-3.5 accent-[var(--accent-primary)] cursor-pointer"
                          />
                        </td>
                        <td className="px-4 py-4">
                          <Link href={`/stocks/${encodeURIComponent(row.symbol)}`} className="font-bold text-sm text-[var(--foreground)] tabular-nums group-hover:text-[var(--accent-cyan)] transition-colors">
                            {row.symbol.split('.')[0]}
                          </Link>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-xs font-medium text-[var(--text-secondary)] truncate max-w-[120px] block uppercase">
                            {row.name}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right hidden sm:table-cell">
                          {price && (
                            <div className="flex justify-end">
                              <Sparkline
                                data={[parseFloat(price.open), parseFloat(price.high), parseFloat(price.low), parseFloat(price.close)]}
                                color={isUp ? "var(--stock-up)" : "var(--stock-down)"}
                                width={60}
                                height={20}
                              />
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-4 text-right tabular-nums text-sm font-bold ${isUp ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}>
                          {row.loading ? (
                            <div className="inline-block w-4 h-4 border-2 border-[var(--border-subtle)] border-t-[var(--accent-cyan)] rounded-full animate-spin" />
                          ) : price ? (
                            parseFloat(price.close).toLocaleString(undefined, { minimumFractionDigits: 2 })
                          ) : "--"}
                        </td>
                        <td className="px-4 py-4 text-right">
                          {price && (
                            <div className={`inline-block px-2 py-0.5 text-[11px] font-bold tabular-nums min-w-[60px] text-center ${isUp ? "bg-[var(--stock-up-bg)] text-[var(--stock-up)]" : "bg-[var(--stock-down-bg)] text-[var(--stock-down)]"}`}>
                              {isUp ? "+" : ""}{changePct.toFixed(2)}%
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-[11px] font-bold text-[var(--text-secondary)] hidden md:table-cell uppercase">
                          {price?.market || "Global"}
                        </td>
                        <td className="px-4 py-4 text-right">
                          <div className="flex justify-end items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Link href={`/stocks/${encodeURIComponent(row.symbol)}`} className="text-[10px] font-bold text-[var(--accent-cyan)] hover:underline">
                              ANALYZE
                            </Link>
                            <button 
                              onClick={() => remove(row.symbol)}
                              className="text-[var(--text-muted)] hover:text-red-500 transition-colors"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </GlassPanel>
        )}
      </main>
    </div>
  );
}
