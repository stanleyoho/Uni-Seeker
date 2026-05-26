"use client";

// ---------------------------------------------------------------------------
// Watchlist page — WATCH-001 / Round 5.2
//
// Source of truth: server (TanStack Query via useWatchlistApi). The legacy
// localStorage-based useWatchlist hook is still exported from
// `@/hooks/use-watchlist` for backward compatibility with other surfaces,
// but this page no longer imports it.
//
// Tier gating: Free users are capped at 10 entries (enforced server-side
// via 403 watchlist_limit_exceeded). We mirror that cap in the UI by
// disabling additions at the limit and rendering a soft warning badge
// starting at 80% capacity.
//
// CSV import/export is intentionally disabled in this round — the API
// surface only supports single-symbol add/remove and the legacy CSV path
// wrote to localStorage. Bulk add lands in Phase 4+. The buttons remain
// rendered (with disabled styling + tooltip) so the layout is stable for
// when bulk-add comes online.
// ---------------------------------------------------------------------------

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/context";
import {
  useWatchlistApi,
  useRemoveFromWatchlist,
} from "@/hooks/use-watchlist-api";
import {
  fetchPrices,
  ApiError,
  type StockPrice,
  type WatchlistItem,
} from "@/lib/api-client";
import { downloadCSV } from "@/lib/csv-export";
import {
  hasLegacyWatchlist,
  migrateLocalWatchlistToApi,
  type MigrationResult,
} from "@/lib/watchlist-migration";
import { useAuth } from "@/contexts/auth-context";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { Sparkline } from "@/components/stratos/charts";

import { AmbientBackground } from "@/components/stratos/ambient";

interface WatchlistRowData {
  symbol: string;
  id: number;
  stock_name: string | null;
  created_at: string;
  price?: StockPrice | null;
  loading: boolean;
}

type SortKey = "symbol" | "change" | "volume";

const FREE_TIER_LIMIT = 10;
const FREE_TIER_WARN_THRESHOLD = 8; // 80% of cap

/**
 * Map backend detail strings (and ApiError statuses) to user-facing zh-TW
 * messages. Keeps the markup tidy by centralising the cases handlers care
 * about: 403 tier cap, 404 unknown symbol, 422 validation, 401 auth.
 */
function describeMutationError(err: unknown): string {
  if (err instanceof ApiError) {
    // Backend returns `detail` as the snake_case identifier — apiFetch
    // surfaces that as `err.message`.
    if (err.status === 403 && err.message.includes("watchlist_limit_exceeded")) {
      return "已達 Free tier 上限 10 檔。升級 Pro 解鎖無限。";
    }
    if (err.status === 404) {
      return "找不到該股代號。";
    }
    if (err.status === 409) {
      return "該股票已在 Watchlist 中。";
    }
    if (err.status === 422) {
      return "代號格式錯誤。";
    }
    if (err.status === 401) {
      return "登入逾期，請重新登入。";
    }
    return err.message || "操作失敗，請稍後再試。";
  }
  return "網路異常，請稍後再試。";
}

export default function WatchlistPage() {
  const { t } = useI18n();
  const { user, loading: authLoading } = useAuth();
  const {
    data: watchlistItems = [],
    isLoading: watchlistLoading,
    isError: watchlistError,
    error: watchlistErrorObj,
  } = useWatchlistApi();
  const removeMutation = useRemoveFromWatchlist();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rowData, setRowData] = useState<WatchlistRowData[]>([]);
  const [pricesLoading, setPricesLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<SortKey>("symbol");
  const [bulkError, setBulkError] = useState<string | null>(null);

  // ── localStorage → API migration banner (Round 6) ───────────────────
  // Fires ONCE per mount when the legacy key exists. The utility itself
  // clears the key after running, so subsequent mounts see nothing. We
  // keep `migrationResult` around so the user can read the outcome until
  // they explicitly dismiss the banner.
  const [migrationResult, setMigrationResult] =
    useState<MigrationResult | null>(null);
  const [migrationDismissed, setMigrationDismissed] = useState(false);
  const [migrationRunning, setMigrationRunning] = useState(false);
  const migrationStartedRef = useRef(false);

  // Memoise the symbol list so loadPrices' identity is stable across renders
  // that don't actually change the underlying symbols (TanStack Query returns
  // a fresh array reference on every refetch, even when contents match).
  const symbolsKey = useMemo(
    () => watchlistItems.map((i) => i.symbol).sort().join(","),
    [watchlistItems],
  );

  const loadPrices = useCallback(async () => {
    if (watchlistItems.length === 0) {
      setRowData([]);
      setPricesLoading(false);
      return;
    }
    setPricesLoading(true);
    // Backend WatchlistItemResponse marks `stock_name` as optional + nullable
    // (`string | null | undefined`); local WatchlistRowData uses the narrower
    // `string | null`. Coerce `undefined → null` at this boundary so each
    // row consumer doesn't have to triple-guard.
    const baseRows: WatchlistRowData[] = watchlistItems.map((item) => ({
      symbol: item.symbol,
      id: item.id,
      stock_name: item.stock_name ?? null,
      created_at: item.created_at,
      loading: true,
    }));
    setRowData(baseRows);

    const updated = await Promise.all(
      watchlistItems.map(async (item) => {
        try {
          const res = await fetchPrices(item.symbol, 1);
          return {
            symbol: item.symbol,
            id: item.id,
            stock_name: item.stock_name ?? null,
            created_at: item.created_at,
            price: res.data[0] ?? null,
            loading: false,
          };
        } catch {
          return {
            symbol: item.symbol,
            id: item.id,
            stock_name: item.stock_name ?? null,
            created_at: item.created_at,
            price: null,
            loading: false,
          };
        }
      }),
    );
    setRowData(updated);
    setPricesLoading(false);
  }, [watchlistItems]);

  // Run the legacy localStorage → API migration once on first mount when
  // the user is authenticated. We gate on `user` because the API hook
  // would otherwise 401, and the migration's `listWatchlist` step would
  // fail before we even know what to insert. We also gate on the ref
  // (instead of relying on dependencies) so a re-mount during dev HMR
  // doesn't trigger a second run if state has already been computed.
  useEffect(() => {
    if (!user) return;
    if (migrationStartedRef.current) return;
    if (!hasLegacyWatchlist()) return;
    migrationStartedRef.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mount-time imperative kickoff of a localStorage->API migration; the running flag toggles back to false in the .finally() async callback (which the rule already allows)
    setMigrationRunning(true);
    (async () => {
      try {
        const result = await migrateLocalWatchlistToApi();
        setMigrationResult(result);
      } finally {
        setMigrationRunning(false);
      }
    })();
  }, [user]);

  // Trigger price refresh when the set of symbols changes (not on every
  // array-identity flip from TanStack Query). `loadPrices()` itself
  // calls setRowData/setPricesLoading inside its useCallback body, so
  // the rule treats the call as a sync setState. The semantics are
  // legitimate -- we're subscribing to upstream data change and
  // mirroring it into a richly-shaped local cache that the async fetch
  // continues to update -- so disable inline with rationale.
  useEffect(() => {
    if (symbolsKey.length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- loadPrices internally setStates; this mirrors upstream watchlist data into our local row cache
      loadPrices();
      return;
    }
    setRowData([]);
    setPricesLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolsKey]);

  // Drop selections for symbols that no longer exist on the server.
  // This is a genuine "respond to upstream data change" subscription;
  // there is no derivation alternative because `selected` is also
  // mutated by user clicks on the table. Disable inline with rationale.
  useEffect(() => {
    const currentSymbols = new Set(watchlistItems.map((i) => i.symbol));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- prune mixed real-state when upstream watchlist removes a symbol; selected is also mutated by user clicks so it must remain real state, not a derivation
    setSelected((prev) => {
      const next = new Set([...prev].filter((s) => currentSymbols.has(s)));
      if (next.size !== prev.size) return next;
      return prev;
    });
  }, [watchlistItems]);

  const sortedRows = useMemo(() => {
    const rows = [...rowData];
    switch (sortBy) {
      case "symbol":
        rows.sort((a, b) => a.symbol.localeCompare(b.symbol));
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

  // Bulk remove: fire each DELETE sequentially. The backend has no batch
  // endpoint yet, so we settle().all() to surface any per-symbol failures
  // without aborting the rest. The mutation hook handles cache
  // invalidation on each success.
  const handleBulkRemove = useCallback(async () => {
    if (selected.size === 0) return;
    setBulkError(null);
    const symbols = [...selected];
    const results = await Promise.allSettled(
      symbols.map((sym) => removeMutation.mutateAsync(sym)),
    );
    const failures = results.filter((r) => r.status === "rejected");
    if (failures.length > 0) {
      const first = failures[0] as PromiseRejectedResult;
      setBulkError(
        `${failures.length} 個項目刪除失敗：${describeMutationError(first.reason)}`,
      );
    }
    setSelected(new Set());
  }, [selected, removeMutation]);

  const handleSingleRemove = useCallback(
    (symbol: string) => {
      setBulkError(null);
      removeMutation.mutate(symbol);
    },
    [removeMutation],
  );

  const handleExport = () => {
    const data = (rowData.length > 0 ? rowData : watchlistItems.map((i) => ({
      symbol: i.symbol,
      created_at: i.created_at,
    }))).map((item) => ({
      symbol: item.symbol,
      added_date: item.created_at ? item.created_at.split("T")[0] : "",
    }));
    downloadCSV(data, "watchlist.csv");
  };

  // ── Tier gating ─────────────────────────────────────────────────────────
  // Treat unknown tier (not yet loaded, or unexpected value) the same as
  // FREE — we'd rather block at-the-cap actions than silently exceed.
  const tier = (user?.tier || "").toUpperCase();
  const isFreeTier = !user || tier === "FREE";
  const itemCount = watchlistItems.length;
  const atFreeLimit = isFreeTier && itemCount >= FREE_TIER_LIMIT;
  const nearFreeLimit =
    isFreeTier && !atFreeLimit && itemCount >= FREE_TIER_WARN_THRESHOLD;

  const wl = t.watchlist;

  // ── Auth gate ───────────────────────────────────────────────────────────
  // The watchlist API is auth-gated; once auth has resolved with no user,
  // surface a login CTA instead of leaking a 401 error banner.
  if (!authLoading && !user) {
    return (
      <div className="flex-1 bg-[var(--background)]">
        <AmbientBackground />
        <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6">
          <GlassPanel className="py-24 text-center">
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">
              請先登入以使用 Watchlist
            </p>
            <p className="text-[10px] text-[var(--text-muted)] mt-2 uppercase">
              Watchlist is now backed by your account — sign in to continue
            </p>
            <Link href="/login" className="inline-block mt-6">
              <ClippedButton variant="red-solid" size="md">
                GO TO LOGIN
              </ClippedButton>
            </Link>
          </GlassPanel>
        </main>
      </div>
    );
  }

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
            <div className="flex items-center gap-3 mt-1 flex-wrap">
              <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest uppercase">
                {itemCount} ACTIVE SECURITIES MONITORED
              </p>
              {isFreeTier && (atFreeLimit || nearFreeLimit) && (
                <span
                  className={`inline-block px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest border ${
                    atFreeLimit
                      ? "bg-[var(--stock-down-bg)] text-[var(--stock-down)] border-[var(--stock-down)]"
                      : "bg-[var(--card-hover)] text-[var(--accent-cyan)] border-[var(--accent-cyan)]"
                  }`}
                >
                  {atFreeLimit
                    ? `Free 上限 ${FREE_TIER_LIMIT} / 升級 Pro 解鎖無限`
                    : `接近上限 (${itemCount}/${FREE_TIER_LIMIT})`}
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled
              title="等後端 bulk add（Phase 4+）"
              className="px-4 py-1.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-muted)] opacity-50 cursor-not-allowed"
            >
              IMPORT CSV
            </button>
            {/* Hidden input retained so the layout stays compatible when
                bulk-add lands in Phase 4+. handler intentionally a no-op. */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={() => {
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              className="hidden"
            />
            <button
              onClick={handleExport}
              disabled={itemCount === 0}
              className="px-4 py-1.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:border-[var(--accent-cyan)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              EXPORT CSV
            </button>
            <ClippedButton
              variant="red-solid"
              size="sm"
              onClick={loadPrices}
              disabled={pricesLoading || itemCount === 0}
            >
              {pricesLoading ? "FETCHING..." : "SYNC PRICES"}
            </ClippedButton>
            {selected.size > 0 && (
              <ClippedButton
                variant="red-ghost"
                size="sm"
                onClick={handleBulkRemove}
                disabled={removeMutation.isPending}
              >
                DELETE SELECTED [{selected.size}]
              </ClippedButton>
            )}
          </div>
        </div>

        {/* Migration banner (Round 6) — surfaced once per user when the
            legacy localStorage key existed at mount. Dismissible. */}
        {migrationRunning && (
          <div
            role="status"
            className="mb-4 px-4 py-3 border bg-[var(--card-hover)] border-[var(--accent-cyan)] text-[var(--accent-cyan)] text-xs font-bold uppercase tracking-widest flex items-center gap-3"
          >
            <span className="inline-block w-3 h-3 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full animate-spin" />
            <span>正在將本機 Watchlist 同步至雲端...</span>
          </div>
        )}
        {migrationResult && !migrationDismissed && !migrationRunning && (
          <div
            role="status"
            className="mb-4 px-4 py-3 border bg-[var(--card-hover)] border-[var(--accent-cyan)] text-[var(--text-secondary)] text-xs font-bold uppercase tracking-widest flex items-center justify-between gap-3"
          >
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-[var(--accent-cyan)]">
                Watchlist 已從本機遷移至雲端
              </span>
              <span>新增 {migrationResult.migrated}</span>
              <span className="text-[var(--text-muted)]">
                / 已存在 {migrationResult.skipped}
              </span>
              {migrationResult.failed.length > 0 && (
                <span className="text-[var(--stock-down)]">
                  / 失敗 {migrationResult.failed.length}
                  {migrationResult.failed.some((f) => f.reason === "tier_cap")
                    ? "（已達 Free 上限）"
                    : ""}
                </span>
              )}
            </div>
            <button
              onClick={() => setMigrationDismissed(true)}
              className="text-[10px] font-bold text-[var(--text-muted)] hover:text-[var(--foreground)] uppercase tracking-widest"
              aria-label="dismiss migration notice"
            >
              ✕ DISMISS
            </button>
          </div>
        )}

        {/* Error banner — surfaced for query failure, last-mutation failure,
            and bulk-remove partial failure */}
        {(watchlistError || removeMutation.isError || bulkError) && (
          <div
            role="alert"
            className="mb-4 px-4 py-3 border bg-[var(--stock-down-bg)] border-[var(--stock-down)] text-[var(--stock-down)] text-xs font-bold uppercase tracking-widest"
          >
            {bulkError
              ? bulkError
              : watchlistError
                ? `載入 Watchlist 失敗：${describeMutationError(watchlistErrorObj)}`
                : describeMutationError(removeMutation.error)}
          </div>
        )}

        {/* Sort selector */}
        {itemCount > 0 && (
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
              Sort by
            </span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-[10px] font-bold uppercase tracking-widest px-2 py-1"
            >
              <option value="symbol">Symbol</option>
              <option value="change">Chg%</option>
              <option value="volume">Volume</option>
            </select>
          </div>
        )}

        {/* List Content */}
        {watchlistLoading ? (
          <GlassPanel className="py-24 text-center">
            <div className="inline-block w-8 h-8 border-2 border-[var(--border-subtle)] border-t-[var(--accent-cyan)] rounded-full animate-spin" />
            <p className="text-[10px] text-[var(--text-muted)] mt-4 uppercase tracking-widest">
              Loading watchlist
            </p>
          </GlassPanel>
        ) : itemCount === 0 ? (
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
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest hidden lg:table-cell">Name</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right hidden sm:table-cell">Intraday</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Price</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Chg%</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right hidden md:table-cell">Market</th>
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
                        <td className="px-4 py-4 hidden lg:table-cell">
                          <span className="text-xs text-[var(--text-secondary)] truncate block max-w-[160px]" title={row.stock_name || undefined}>
                            {row.stock_name || "--"}
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
                              onClick={() => handleSingleRemove(row.symbol)}
                              disabled={removeMutation.isPending}
                              className="text-[var(--text-muted)] hover:text-red-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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

// Type re-export retained for callers that imported the row shape from
// this module before the API migration. The shape now matches the API
// `WatchlistItem` (id/symbol/created_at).
export type { WatchlistItem };
