"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchMarketIndices,
  fetchMarketMovers,
  fetchHeatmapData,
  fetchPrices,
  fetchCompanyInfo,
  fetchMarginData,
  fetchFinancialAnalysis,
  fetchLowBaseRanking,
  fetchRevenueAnalysis,
  fetchInstitutional,
  fetchValuationEstimates,
  fetchAiCommentary,
  fetchBuffettIndicator,
  fetchMarketTemperature,
  fetchETFArbitrage,
  type ETFArbitrageQuery,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useMarketIndices() {
  return useQuery({
    queryKey: queryKeys.market.indices(),
    queryFn: fetchMarketIndices,
    staleTime: 2 * 60 * 1000, // 2 min
    refetchInterval: 60_000, // auto-refresh every 1 min
  });
}

export function useMarketMovers(marketFilter?: string) {
  return useQuery({
    queryKey: queryKeys.market.movers(marketFilter),
    queryFn: () => fetchMarketMovers(marketFilter),
    staleTime: 2 * 60 * 1000,
    refetchInterval: 60_000, // auto-refresh every 1 min
  });
}

export function useHeatmap(marketFilter?: string) {
  return useQuery({
    queryKey: queryKeys.market.heatmap(marketFilter),
    queryFn: () => fetchHeatmapData(marketFilter),
    staleTime: 2 * 60 * 1000,
  });
}

// Macro mini-widgets — refreshed every 5 min (matches backend cache TTL).
// Buffett ratio barely moves intra-day; temperature follows the index
// basket which the KPI row already auto-refreshes at 1 min, but we cap
// both at 5 min to avoid pinging the macro endpoints unnecessarily.

export function useBuffettIndicator() {
  return useQuery({
    queryKey: queryKeys.market.buffett(),
    queryFn: fetchBuffettIndicator,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

export function useMarketTemperature() {
  return useQuery({
    queryKey: queryKeys.market.temperature(),
    queryFn: fetchMarketTemperature,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

export function usePrices(symbol: string, limit: number) {
  return useQuery({
    queryKey: queryKeys.stocks.prices(symbol, limit),
    queryFn: () => fetchPrices(symbol, limit),
    staleTime: 60 * 1000,
    enabled: !!symbol,
  });
}

export function useCompanyInfo(symbol: string) {
  return useQuery({
    queryKey: queryKeys.stocks.company(symbol),
    queryFn: () => fetchCompanyInfo(symbol),
    staleTime: 10 * 60 * 1000, // 10 min - rarely changes
    enabled: !!symbol,
  });
}

export function useMarginData(symbol: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.stocks.margin(symbol),
    queryFn: () => fetchMarginData(symbol),
    staleTime: 2 * 60 * 1000,
    enabled: enabled && !!symbol,
  });
}

export function useFinancialAnalysis(symbol: string) {
  return useQuery({
    queryKey: queryKeys.stocks.financials(symbol),
    queryFn: () => fetchFinancialAnalysis(symbol),
    staleTime: 10 * 60 * 1000,
    enabled: !!symbol,
  });
}

export function useRevenue(symbol: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.stocks.revenue(symbol),
    queryFn: () => fetchRevenueAnalysis(symbol),
    staleTime: 10 * 60 * 1000,
    enabled: enabled && !!symbol,
  });
}

export function useInstitutional(symbol: string, startDate: string, endDate: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.stocks.institutional(symbol, startDate, endDate),
    queryFn: () => fetchInstitutional(symbol, startDate, endDate),
    staleTime: 5 * 60 * 1000,
    enabled: enabled && !!symbol && !!startDate && !!endDate,
  });
}

export function useLowBaseRanking(limit = 20) {
  return useQuery({
    queryKey: queryKeys.lowBase.ranking(limit),
    queryFn: () => fetchLowBaseRanking(limit),
    staleTime: 5 * 60 * 1000,
  });
}

// ETF premium / discount monitor — refresh every 2 min to mirror the
// market-movers cadence; NAV itself only updates daily at 17:35 but
// the *market price* leg moves intraday.
export function useETFArbitrage(query: ETFArbitrageQuery = {}) {
  return useQuery({
    queryKey: queryKeys.etfArbitrage.list(
      query.market,
      query.type,
      query.direction,
      query.limit,
    ),
    queryFn: () => fetchETFArbitrage(query),
    staleTime: 2 * 60 * 1000,
    refetchInterval: 2 * 60 * 1000,
  });
}

export function useValuation(symbol: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.stocks.valuation(symbol),
    queryFn: () => fetchValuationEstimates(symbol),
    staleTime: 10 * 60 * 1000,
    enabled: enabled && !!symbol,
  });
}

// AI commentary is server-cached for 4h, so a long client staleTime is
// safe and avoids re-fetching when users tab between Overview / Analysis.
// `retry: false` because a 404 means "no price data yet" — retrying
// won't help and we want the empty-state to render fast.
export function useAiCommentary(symbol: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.stocks.aiCommentary(symbol),
    queryFn: () => fetchAiCommentary(symbol),
    staleTime: 60 * 60 * 1000, // 1h client cache; server keeps 4h
    enabled: enabled && !!symbol,
    retry: false,
  });
}
