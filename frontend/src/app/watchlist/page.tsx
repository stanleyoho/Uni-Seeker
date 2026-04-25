"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { useWatchlist, type WatchlistItem } from "@/hooks/use-watchlist";
import { fetchPrices, type StockPrice } from "@/lib/api-client";
import { ChangeBadge, MarketBadge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";

interface WatchlistRowData extends WatchlistItem {
  price?: StockPrice | null;
  loading: boolean;
}

export default function WatchlistPage() {
  const { t } = useI18n();
  const { items, remove } = useWatchlist();
  const [rowData, setRowData] = useState<WatchlistRowData[]>([]);
  const [loading, setLoading] = useState(true);

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

  const wl = t.watchlist;

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">{wl?.title ?? "Watchlist"}</h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">
            {wl?.subtitle ?? `${items.length} stocks tracked`}
          </p>
        </div>
        {items.length > 0 && (
          <button
            onClick={loadPrices}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] text-white transition-all duration-200 disabled:opacity-50"
          >
            {loading ? (wl?.refreshing ?? "...") : (wl?.refresh ?? "Refresh")}
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title={wl?.emptyTitle ?? "No stocks in watchlist"}
          message={wl?.emptyMessage ?? "Search for a stock and click the star icon to add it here"}
          action={
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[var(--accent-blue)] text-white rounded-lg hover:bg-[var(--accent-blue-hover)] transition-all"
            >
              {wl?.goSearch ?? "Search Stocks"}
            </Link>
          }
        />
      ) : loading && rowData.every((r) => r.loading) ? (
        <LoadingSpinner text={wl?.loading ?? "Loading prices..."} size="sm" />
      ) : (
        <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg overflow-hidden">
          {/* Table header */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border-subtle)] text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
            <span className="w-6" />
            <span className="flex-1">Symbol</span>
            <span className="w-24 text-right">Price</span>
            <span className="w-28 text-right">Change</span>
          </div>
          {rowData.map((row) => {
            const price = row.price;
            const change = price ? parseFloat(price.change) : 0;
            const changePct = price ? price.change_percent : "0";

            return (
              <div
                key={row.symbol}
                className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[var(--card-hover)] transition-colors duration-100 group"
              >
                {/* Remove button */}
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
                    <span className="text-white font-semibold text-sm group-hover:text-[var(--accent-blue)] transition-colors">
                      {row.symbol.replace(".TW", "").replace(".TWO", "")}
                    </span>
                    <span className="text-[var(--text-muted)] text-xs truncate">{row.name}</span>
                    <MarketBadge market={row.market} />
                  </div>
                </Link>

                {/* Price + Change */}
                {row.loading ? (
                  <div className="w-3 h-3 border-2 border-[var(--border-color)] border-t-[var(--accent-blue)] rounded-full animate-spin" />
                ) : price ? (
                  <div className="flex items-center gap-2">
                    <span className="text-white text-sm font-semibold mono-nums w-24 text-right">
                      {parseFloat(price.close).toLocaleString()}
                    </span>
                    <div className="w-28 flex justify-end">
                      <ChangeBadge change={change} changePct={changePct} />
                    </div>
                  </div>
                ) : (
                  <span className="text-[var(--text-muted)] text-xs mono-nums">--</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
