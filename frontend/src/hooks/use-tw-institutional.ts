"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchRecentSignals,
  fetchTwInstitutionalSymbol,
  fetchTwInstitutionalTopNet,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

/**
 * TW 三大法人 leaderboard for the home mini-tile.
 *
 * 5-min staleTime + 5-min refetchInterval — institutional flow is
 * published once daily after 17:00 Taipei, so polling more aggressively
 * adds zero signal value. Long stale window also dampens FinMind quota
 * pressure when many tabs are open.
 */
export function useTwInstitutionalTopNet(params: {
  kind?: "foreign" | "trust" | "dealer" | "total";
  direction?: "buy" | "sell";
  date?: string;
  limit?: number;
} = {}) {
  const kind = params.kind ?? "foreign";
  const direction = params.direction ?? "buy";
  const limit = params.limit ?? 5;
  return useQuery({
    queryKey: queryKeys.twInstitutional.topNet(
      kind,
      direction,
      params.date,
      limit,
    ),
    queryFn: () =>
      fetchTwInstitutionalTopNet({
        kind,
        direction,
        date: params.date,
        limit,
      }),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

export function useTwInstitutionalSymbol(symbol: string, days = 30) {
  return useQuery({
    queryKey: queryKeys.twInstitutional.symbol(symbol, days),
    queryFn: () => fetchTwInstitutionalSymbol(symbol, days),
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  });
}

/**
 * Pre-market signal board hook.
 *
 * lookbackHours default = 20 covers from yesterday's market close
 * (13:30 Taipei) through the morning open (09:00 Taipei). Matches the
 * "open the app at 8:30, see what fired overnight" use case.
 */
export function useRecentSignals(
  lookbackHours = 20,
  top = 10,
) {
  return useQuery({
    queryKey: queryKeys.signals.recent(lookbackHours, top),
    queryFn: () => fetchRecentSignals({ lookbackHours, top }),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  });
}
