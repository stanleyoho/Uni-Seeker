"use client";

// ---------------------------------------------------------------------------
// Watchlist API hooks — WATCH-001 / Round 5.1 (+ Round 6 bulk)
//
// Server-backed watchlist (TanStack Query) — separate from the legacy
// localStorage-based `useWatchlist` in ./use-watchlist.ts. The localStorage
// hook is deprecated as of Round 6 (see file-level JSDoc there) but still
// imported by /home and /stocks/[symbol]; do NOT delete it until those
// pages migrate.
//
// Error handling convention: mutations intentionally do NOT swallow errors.
// Callers should read `mutation.error` / `mutation.isError` to surface
// tier-cap (403 watchlist_limit_exceeded, or 403 limit_exceeded:max_watchlist
// for bulk), conflict (409 watchlist_already_exists), and not-found (404
// stock_not_found) responses to the user.
// ---------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addToWatchlist,
  bulkAddToWatchlist,
  listWatchlist,
  removeFromWatchlist,
  type WatchlistBulkAddResponse,
  type WatchlistItem,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useWatchlistApi() {
  return useQuery({
    queryKey: queryKeys.watchlist.list(),
    queryFn: listWatchlist,
    staleTime: 30 * 1000,
    placeholderData: (): WatchlistItem[] => [],
  });
}

export function useAddToWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => addToWatchlist(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.watchlist.all });
    },
  });
}

/**
 * Bulk-add up to 20 symbols. The backend is atomic on the quota gate:
 * if the projected post-insert count exceeds the Free cap, NOTHING is
 * inserted and the mutation rejects with a 403 ApiError. Per-row issues
 * (unknown symbol, etc.) are reported inside the 201 envelope's
 * `errors[]` field — callers MUST inspect both `error` AND `data.errors`.
 *
 * Invalidates the same query key as the single-symbol mutation so the
 * list view refetches after a successful batch.
 */
export function useBulkAddToWatchlist() {
  const qc = useQueryClient();
  return useMutation<WatchlistBulkAddResponse, Error, string[]>({
    mutationFn: (symbols: string[]) => bulkAddToWatchlist(symbols),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.watchlist.all });
    },
  });
}

export function useRemoveFromWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => removeFromWatchlist(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.watchlist.all });
    },
  });
}
