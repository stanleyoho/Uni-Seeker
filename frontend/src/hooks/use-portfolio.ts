"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  runPortfolioBacktest,
  type PortfolioBacktestResponse,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

/* ── Types ── */

export interface PortfolioAllocation {
  symbol: string;
  weight: number; // 0-100
  strategy: string;
}

export type RebalanceMode = "none" | "periodic" | "threshold";

export interface PortfolioBacktestParams {
  allocations: PortfolioAllocation[];
  rebalance_mode: RebalanceMode;
  rebalance_period_days?: number;
  rebalance_threshold_pct?: number;
  initial_capital: number;
}

export interface PortfolioStockMetric {
  symbol: string;
  weight: number;
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  win_rate: number;
  max_drawdown: number;
}

export interface RebalanceEvent {
  date: string;
  reason: string;
  adjustments: { symbol: string; from_weight: number; to_weight: number }[];
}

export interface PortfolioBacktestResult {
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  portfolio_equity: number[];
  stock_equities: Record<string, number[]>;
  stock_metrics: PortfolioStockMetric[];
  rebalance_log: RebalanceEvent[];
  dates: string[];
}

export interface PortfolioHistoryEntry {
  id: string;
  created_at: string;
  params: PortfolioBacktestParams;
  result: PortfolioBacktestResult;
}

/* ── Map API response to frontend types ── */

function mapApiResponse(
  apiRes: PortfolioBacktestResponse,
  params: PortfolioBacktestParams,
): PortfolioBacktestResult {
  const metrics = apiRes.portfolio_metrics;
  const equityCurve = apiRes.portfolio_equity_curve;

  // Backend types individual_metrics as Record<string, Record<string, unknown>>.
  // Narrow each cell to number with a runtime guard.
  const asNum = (v: unknown): number => (typeof v === "number" ? v : 0);

  // Build stock_metrics from individual_metrics + original allocations
  const stockMetrics: PortfolioStockMetric[] = params.allocations.map((alloc) => {
    const m = apiRes.individual_metrics[alloc.symbol] ?? {};
    return {
      symbol: alloc.symbol,
      weight: alloc.weight,
      total_return: asNum(m.total_return),
      annualized_return: asNum(m.annualized_return),
      sharpe_ratio: asNum(m.sharpe_ratio),
      win_rate: asNum(m.win_rate),
      max_drawdown: asNum(m.max_drawdown),
    };
  });

  // Map rebalance log entries
  const rebalanceLog: RebalanceEvent[] = (apiRes.rebalance_log ?? []).map((entry) => ({
    date: (entry.date as string) ?? "",
    reason: (entry.reason as string) ?? "",
    adjustments: (entry.adjustments as RebalanceEvent["adjustments"]) ?? [],
  }));

  // Generate date labels based on equity curve length
  const days = equityCurve.length;
  const dates: string[] = [];
  const start = new Date("2024-01-02");
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + Math.floor(i * 365 / Math.max(days, 1)));
    dates.push(d.toISOString().slice(0, 10));
  }

  return {
    total_return: metrics.total_return ?? 0,
    annualized_return: metrics.annualized_return ?? 0,
    max_drawdown: metrics.max_drawdown ?? 0,
    // Backend field is `sharpe` (PortfolioMetricsResponse); maps to frontend `sharpe_ratio`.
    sharpe_ratio: metrics.sharpe ?? 0,
    portfolio_equity: equityCurve,
    stock_equities: apiRes.individual_equity_curves ?? {},
    stock_metrics: stockMetrics,
    rebalance_log: rebalanceLog,
    dates,
  };
}

/* ── Hooks ── */

export function usePortfolioBacktest() {
  return useMutation({
    mutationFn: async (params: PortfolioBacktestParams): Promise<PortfolioBacktestResult> => {
      // Build rebalance_config from flat params
      const rebalanceConfig: Record<string, unknown> = {};
      if (params.rebalance_mode === "periodic" && params.rebalance_period_days) {
        rebalanceConfig.period_days = params.rebalance_period_days;
      }
      if (params.rebalance_mode === "threshold" && params.rebalance_threshold_pct) {
        rebalanceConfig.threshold_pct = params.rebalance_threshold_pct;
      }

      try {
        const apiRes = await runPortfolioBacktest({
          // params is required by PortfolioAllocationInput (Pydantic default {}).
          allocations: params.allocations.map((a) => ({
            symbol: a.symbol,
            weight: a.weight,
            strategy: a.strategy,
            params: {},
          })),
          rebalance_mode: params.rebalance_mode,
          rebalance_config: rebalanceConfig,
          initial_capital: params.initial_capital,
        });
        return mapApiResponse(apiRes, params);
      } catch (error) {
        throw error instanceof Error ? error : new Error("Portfolio backtest failed");
      }
    },
  });
}

export function usePortfolioHistory() {
  return useQuery({
    queryKey: queryKeys.portfolio.history(),
    queryFn: async (): Promise<PortfolioHistoryEntry[]> => {
      // No backend endpoint for portfolio history yet
      return [];
    },
    staleTime: 5 * 60 * 1000,
  });
}
