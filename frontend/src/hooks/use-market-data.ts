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
} from "@/lib/api-client";

export function useMarketIndices() {
  return useQuery({
    queryKey: ["market", "indices"],
    queryFn: fetchMarketIndices,
    staleTime: 2 * 60 * 1000, // 2 min
  });
}

export function useMarketMovers(marketFilter?: string) {
  return useQuery({
    queryKey: ["market", "movers", marketFilter],
    queryFn: () => fetchMarketMovers(marketFilter),
    staleTime: 2 * 60 * 1000,
  });
}

export function useHeatmap(marketFilter?: string) {
  return useQuery({
    queryKey: ["heatmap", marketFilter],
    queryFn: () => fetchHeatmapData(marketFilter),
    staleTime: 2 * 60 * 1000,
  });
}

export function usePrices(symbol: string, limit: number) {
  return useQuery({
    queryKey: ["prices", symbol, limit],
    queryFn: () => fetchPrices(symbol, limit),
    staleTime: 60 * 1000,
    enabled: !!symbol,
  });
}

export function useCompanyInfo(symbol: string) {
  return useQuery({
    queryKey: ["company", symbol],
    queryFn: () => fetchCompanyInfo(symbol),
    staleTime: 10 * 60 * 1000, // 10 min - rarely changes
    enabled: !!symbol,
  });
}

export function useMarginData(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["margin", symbol],
    queryFn: () => fetchMarginData(symbol),
    staleTime: 2 * 60 * 1000,
    enabled: enabled && !!symbol,
  });
}

export function useFinancialAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["financials", symbol],
    queryFn: () => fetchFinancialAnalysis(symbol),
    staleTime: 10 * 60 * 1000,
    enabled: !!symbol,
  });
}

export function useRevenue(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ["revenue", symbol],
    queryFn: () => fetchRevenueAnalysis(symbol),
    staleTime: 10 * 60 * 1000,
    enabled: enabled && !!symbol,
  });
}

export function useInstitutional(symbol: string, startDate: string, endDate: string, enabled = true) {
  return useQuery({
    queryKey: ["institutional", symbol, startDate, endDate],
    queryFn: () => fetchInstitutional(symbol, startDate, endDate),
    staleTime: 5 * 60 * 1000,
    enabled: enabled && !!symbol && !!startDate && !!endDate,
  });
}

export function useLowBaseRanking(limit = 20) {
  return useQuery({
    queryKey: ["low-base", limit],
    queryFn: () => fetchLowBaseRanking(limit),
    staleTime: 5 * 60 * 1000,
  });
}
