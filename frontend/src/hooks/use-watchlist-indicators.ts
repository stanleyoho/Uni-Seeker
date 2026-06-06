"use client";

// ---------------------------------------------------------------------------
// useWatchlistIndicators — live price + indicators for the watchlist panel.
//
// A2 "Stock.Indicators streaming hub" (scoped v1). We poll rather than stream:
// the project has no symbol-keyed push pipeline (the existing /ws endpoint is
// a generic echo broadcaster), and TanStack Query's `refetchInterval` is the
// established refetch pattern across the app. Polling keeps the surface area
// small and the failure mode obvious.
//
// The hook is intentionally thin: it batches the user's current watchlist
// symbols into ONE request to POST /watchlist/indicators and refetches on a
// fixed interval. Components read `data` (per-symbol snapshots) plus the
// standard query flags. `dataUpdatedAt` lets the panel flash a "fresh update"
// indicator without any extra bookkeeping.
// ---------------------------------------------------------------------------

import { useQuery } from "@tanstack/react-query";
import {
  fetchWatchlistIndicators,
  type WatchlistLiveIndicator,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

/** Default poll cadence (ms). Slow enough to be polite to yfinance's TTL
 *  cache (60s server-side), fast enough to feel "live" on a watchlist. */
export const WATCHLIST_POLL_INTERVAL_MS = 15_000;

export interface UseWatchlistIndicatorsOptions {
  /** Override the poll cadence (mostly for tests / power-user settings). */
  refetchIntervalMs?: number;
  /** Disable the query entirely (e.g. unauthenticated or empty watchlist). */
  enabled?: boolean;
}

/**
 * Live indicator snapshots for `symbols`, refreshed on an interval.
 *
 * Pass the symbols currently on the user's watchlist. The query is disabled
 * automatically when the list is empty (the backend would 422 on an empty
 * batch) or when `enabled` is false.
 *
 * `staleTime` is set to the poll interval so manual refetches / window-focus
 * refetches don't double-fire inside one cadence window.
 */
export function useWatchlistIndicators(
  symbols: string[],
  options: UseWatchlistIndicatorsOptions = {},
) {
  const interval = options.refetchIntervalMs ?? WATCHLIST_POLL_INTERVAL_MS;
  const enabled = (options.enabled ?? true) && symbols.length > 0;

  return useQuery<WatchlistLiveIndicator[]>({
    queryKey: queryKeys.watchlist.indicators(symbols),
    queryFn: () => fetchWatchlistIndicators(symbols),
    enabled,
    // Poll while mounted. We keep polling in the background so the panel is
    // already fresh when the user tabs back, rather than showing a stale
    // snapshot until the next focus refetch.
    refetchInterval: interval,
    refetchIntervalInBackground: false,
    staleTime: interval,
    // Keep the previous snapshot visible while the next poll is in flight so
    // the panel never flickers to a loading state on every tick.
    placeholderData: (prev) => prev,
  });
}
