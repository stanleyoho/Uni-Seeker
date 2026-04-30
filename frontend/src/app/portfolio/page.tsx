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

interface WatchlistRowData extends WatchlistItem {
  price?: StockPrice | null;
  loading: boolean;
}

type SortKey = "symbol" | "name" | "change";

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

  const sortOptions: { key: SortKey; label: string }[] = [
    { key: "symbol", label: "代號" },
    { key: "name", label: "名稱" },
    { key: "change", label: "漲跌幅" },
  ];

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-[var(--foreground)] tracking-tight">
            {wl?.title ?? "Watchlist"}
          </h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">
            {wl?.subtitle ?? `${items.length} stocks tracked`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {items.length > 0 && (
            <>
              <ClippedButton variant="cyan-ghost" size="sm" onClick={handleExport}>
                匯出 CSV
              </ClippedButton>
              <label className="cursor-pointer">
                <ClippedButton variant="cyan-ghost" size="sm" onClick={() => fileInputRef.current?.click()}>
                  匯入 CSV
                </ClippedButton>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleImport}
                  className="hidden"
                />
              </label>
            </>
          )}
          {items.length > 0 && (
            <>
              {/* Sort dropdown */}
              <div className="flex items-center gap-1">
                <label htmlFor="sort-select" className="text-[10px] text-[var(--text-muted)]">
                  排序
                </label>
                <select
                  id="sort-select"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as SortKey)}
                  className="px-2 py-1 text-xs bg-[var(--glass-bg)] border border-[var(--border-color)] text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-cyan)]"
                  style={{ clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))" }}
                >
                  {sortOptions.map((opt) => (
                    <option key={opt.key} value={opt.key}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Bulk remove */}
              {selected.size > 0 && (
                <ClippedButton variant="red-solid" size="sm" onClick={handleBulkRemove}>
                  刪除已選 ({selected.size})
                </ClippedButton>
              )}

              <ClippedButton
                variant="red-ghost"
                size="sm"
                onClick={loadPrices}
                disabled={loading}
              >
                {loading ? (wl?.refreshing ?? "...") : (wl?.refresh ?? "Refresh")}
              </ClippedButton>
            </>
          )}
        </div>
      </div>

      {/* Empty State */}
      {items.length === 0 ? (
        <GlassPanel>
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-16 h-16 mx-auto mb-4 flex items-center justify-center"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--border-color)",
                clipPath: "polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))",
              }}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" strokeWidth="1.5">
                <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
            </div>
            <p className="text-[var(--foreground)] text-sm font-semibold mb-1">
              {wl?.emptyTitle ?? "No stocks in watchlist"}
            </p>
            <p className="text-[var(--text-muted)] text-xs mb-4">
              {wl?.emptyMessage ?? "Search for a stock and click the star icon to add it here"}
            </p>
            <Link href="/">
              <ClippedButton variant="red-solid" size="sm">
                {wl?.goSearch ?? "Search Stocks"}
              </ClippedButton>
            </Link>
          </div>
        </GlassPanel>
      ) : loading && rowData.every((r) => r.loading) ? (
        <GlassPanel>
          <div className="flex items-center justify-center py-16">
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 border-2 border-[var(--border-color)] border-t-[var(--accent-cyan)] rounded-full animate-spin" />
              <span className="text-[var(--text-muted)] text-sm">{wl?.loading ?? "Loading prices..."}</span>
            </div>
          </div>
        </GlassPanel>
      ) : (
        /* Watchlist Table */
        <GlassPanel noPadding>
          {/* Table header */}
          <div
            className="flex items-center gap-2 px-4 py-2.5 text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-semibold"
            style={{ borderBottom: "1px solid var(--border-color)" }}
          >
            <label className="w-5 shrink-0 flex items-center justify-center">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someSelected;
                }}
                onChange={toggleSelectAll}
                className="w-3.5 h-3.5 accent-[var(--accent-primary)] cursor-pointer"
                aria-label="Select all"
              />
            </label>
            <span className="w-6" />
            <span className="flex-1">Symbol</span>
            <span className="w-20 text-right hidden sm:block">Sparkline</span>
            <span className="w-24 text-right">Price</span>
            <span className="w-28 text-right">Change</span>
          </div>

          {/* Table rows */}
          {sortedRows.map((row) => {
            const price = row.price;
            const change = price ? parseFloat(price.change) : 0;
            const changePct = price ? parseFloat(price.change_percent) : 0;
            const isSelected = selected.has(row.symbol);
            const sparkColor = change >= 0 ? "var(--stock-up)" : "var(--stock-down)";

            return (
              <div
                key={row.symbol}
                className="flex items-center gap-2 px-4 py-2.5 transition-colors duration-100 group"
                style={{
                  borderBottom: "1px solid var(--border-color)",
                  borderLeft: isSelected ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  background: isSelected ? "rgba(238, 63, 44, 0.05)" : undefined,
                }}
              >
                {/* Checkbox */}
                <label className="w-5 shrink-0 flex items-center justify-center">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(row.symbol)}
                    className="w-3.5 h-3.5 accent-[var(--accent-primary)] cursor-pointer"
                    aria-label={`Select ${row.symbol}`}
                  />
                </label>

                {/* Star remove button */}
                <button
                  onClick={() => remove(row.symbol)}
                  className="text-yellow-400/70 hover:text-yellow-400 transition-colors w-6 shrink-0"
                  title={wl?.remove ?? "Remove from watchlist"}
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                  </svg>
                </button>

                {/* Symbol + Name */}
                <Link
                  href={`/stocks/${encodeURIComponent(row.symbol)}`}
                  className="flex-1 min-w-0"
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-[var(--foreground)] font-bold text-sm group-hover:text-[var(--accent-primary)] transition-colors">
                      {row.symbol.replace(".TW", "").replace(".TWO", "")}
                    </span>
                    <span className="text-[var(--text-muted)] text-xs truncate">{row.name}</span>
                    <MarketBadge market={row.market} />
                  </div>
                </Link>

                {/* Sparkline */}
                <div className="w-20 hidden sm:flex justify-end">
                  {price && (
                    <Sparkline
                      data={[
                        parseFloat(price.open),
                        parseFloat(price.high),
                        parseFloat(price.low),
                        parseFloat(price.close),
                      ]}
                      color={sparkColor}
                      width={64}
                      height={20}
                    />
                  )}
                </div>

                {/* Price + Change */}
                {row.loading ? (
                  <div className="w-3 h-3 border-2 border-[var(--border-color)] border-t-[var(--accent-cyan)] rounded-full animate-spin" />
                ) : price ? (
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--foreground)] text-sm font-semibold tabular-nums w-24 text-right">
                      {parseFloat(price.close).toLocaleString()}
                    </span>
                    <div className="w-28 flex justify-end">
                      <span
                        className="text-xs font-semibold tabular-nums px-2 py-0.5"
                        style={{
                          color: change > 0 ? "var(--stock-up)" : change < 0 ? "var(--stock-down)" : "var(--text-muted)",
                          background: change > 0 ? "rgba(16,185,129,0.1)" : change < 0 ? "rgba(239,68,68,0.1)" : "transparent",
                          clipPath: "polygon(0 0, calc(100% - 4px) 0, 100% 4px, 100% 100%, 4px 100%, 0 calc(100% - 4px))",
                        }}
                      >
                        {change > 0 ? "+" : ""}{changePct.toFixed(2)}%
                      </span>
                    </div>
                  </div>
                ) : (
                  <span className="text-[var(--text-muted)] text-xs tabular-nums">--</span>
                )}
              </div>
            );
          })}
        </GlassPanel>
      )}
    </div>
  );
}
