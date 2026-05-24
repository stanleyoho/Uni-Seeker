"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  runSignalScan as apiRunSignalScan,
  fetchStockSignals as apiFetchStockSignals,
  type ApiStockSignal,
  type ScanResponse,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

// ---- Types (preserved for consumer compatibility) ----

export type SignalAction = "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL";

export interface StrategySignal {
  strategy: string;
  action: SignalAction;
  reason: string;
}

export interface StockSignal {
  symbol: string;
  name: string;
  compositeAction: SignalAction;
  score: number; // -1 to +1
  signals: StrategySignal[];
  scannedAt: string;
}

export interface ScanResult {
  stocks: StockSignal[];
  totalScanned: number;
  scannedAt: string;
}

// ---- Map API response to frontend types ----

function mapApiSignal(apiSignal: ApiStockSignal, scanDate: string): StockSignal {
  return {
    symbol: apiSignal.symbol,
    name: apiSignal.name,
    compositeAction: apiSignal.composite_action as SignalAction,
    score: apiSignal.score,
    signals: (apiSignal.signals ?? []).map((s) => ({
      strategy: s.strategy,
      action: s.action as SignalAction,
      reason: s.reason,
    })),
    scannedAt: scanDate,
  };
}

function mapScanResponse(apiRes: ScanResponse): ScanResult {
  const scanDate = apiRes.scan_date ?? new Date().toISOString();
  return {
    stocks: (apiRes.results ?? []).map((s) => mapApiSignal(s, scanDate)),
    totalScanned: apiRes.total_scanned ?? 0,
    scannedAt: scanDate,
  };
}

// ---- Hooks ----

export function useSignalScan(config?: { strategyKeys?: string[] }) {
  return useQuery({
    queryKey: queryKeys.scanner.scan(config?.strategyKeys),
    queryFn: async (): Promise<ScanResult> => {
      try {
        const apiRes = await apiRunSignalScan({
          strategy_keys: config?.strategyKeys,
        });
        return mapScanResponse(apiRes);
      } catch {
        return { stocks: [], totalScanned: 0, scannedAt: new Date().toISOString() };
      }
    },
    staleTime: 5 * 60 * 1000,
    enabled: false, // manual trigger only
  });
}

export function useStockSignals(symbol: string) {
  return useQuery({
    queryKey: queryKeys.scanner.stock(symbol),
    queryFn: async (): Promise<StockSignal | null> => {
      try {
        const apiSignal = await apiFetchStockSignals(symbol);
        return mapApiSignal(apiSignal, new Date().toISOString());
      } catch {
        return null;
      }
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  });
}

export function useRunScan() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (strategyKeys?: string[]): Promise<ScanResult> => {
      const apiRes = await apiRunSignalScan({
        strategy_keys: strategyKeys,
      });
      return mapScanResponse(apiRes);
    },
    onSuccess: (data, strategyKeys) => {
      queryClient.setQueryData(queryKeys.scanner.scan(strategyKeys), data);
    },
  });
}
