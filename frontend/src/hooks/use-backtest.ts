"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchStrategies,
  runBacktest,
  fetchQueueStatus,
  fetchBacktestHistory,
  enqueueBacktestJob,
  type StrategyInfo,
  type BacktestResult,
  type QueueStatus,
  type BacktestHistoryResponse,
  type JobStatus,
  type JobEnqueueRequest,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

/**
 * Fetch available backtest strategies.
 */
export function useStrategies() {
  return useQuery<StrategyInfo[]>({
    queryKey: queryKeys.backtest.strategies(),
    queryFn: fetchStrategies,
    staleTime: 10 * 60 * 1000, // strategies rarely change
  });
}

/**
 * Poll the backtest queue. Refetches every 3s when there are running/pending jobs.
 */
export function useBacktestQueue() {
  return useQuery<QueueStatus>({
    queryKey: queryKeys.backtest.queue(),
    queryFn: async () => {
      try {
        return await fetchQueueStatus();
      } catch {
        return { jobs: [], running_count: 0, pending_count: 0 };
      }
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.running_count > 0 || data.pending_count > 0)) {
        return 3000;
      }
      return false;
    },
    staleTime: 1000,
    placeholderData: { jobs: [], running_count: 0, pending_count: 0 },
  });
}

/**
 * Fetch backtest history with optional symbol filter.
 */
export function useBacktestHistory(symbol?: string, limit: number = 50) {
  return useQuery<BacktestHistoryResponse>({
    queryKey: queryKeys.backtest.history(symbol, limit),
    queryFn: async () => {
      try {
        return await fetchBacktestHistory(symbol, limit);
      } catch {
        return { results: [], total: 0 };
      }
    },
    staleTime: 5 * 60 * 1000,
    placeholderData: { results: [], total: 0 },
  });
}

/**
 * Mutation for running a backtest immediately.
 */
export function useRunBacktest() {
  const queryClient = useQueryClient();

  return useMutation<
    BacktestResult,
    Error,
    {
      symbol: string;
      strategy: string;
      params?: Record<string, unknown>;
      initial_capital?: number;
      position_size?: number;
      stop_loss?: number | null;
      take_profit?: number | null;
    }
  >({
    mutationFn: runBacktest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.backtest.all });
    },
  });
}

/**
 * Mutation for enqueuing a backtest job.
 */
export function useEnqueueBacktest() {
  const queryClient = useQueryClient();

  return useMutation<JobStatus, Error, JobEnqueueRequest>({
    mutationFn: enqueueBacktestJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.backtest.queue() });
    },
  });
}
