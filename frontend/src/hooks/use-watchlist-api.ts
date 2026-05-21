"use client";

// ---------------------------------------------------------------------------
// Watchlist API hooks — WATCH-001 / Round 5.1
//
// Server-backed watchlist (TanStack Query) — separate from the legacy
// localStorage-based `useWatchlist` in ./use-watchlist.ts. The localStorage
// hook is still wired into /portfolio/page.tsx; do NOT mix the two until
// the portfolio page migration (A2's job) lands.
//
// Error handling convention: mutations intentionally do NOT swallow errors.
// Callers should read `mutation.error` / `mutation.isError` to surface
// tier-cap (403 watchlist_limit_exceeded), conflict (409
// watchlist_already_exists), and not-found (404 stock_not_found) responses
// to the user.
// ---------------------------------------------------------------------------

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addToWatchlist,
  listWatchlist,
  removeFromWatchlist,
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

export function useRemoveFromWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => removeFromWatchlist(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.watchlist.all });
    },
  });
}
