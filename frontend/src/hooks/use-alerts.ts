"use client";

/**
 * Alert rules — React Query hooks (UNI-ALERT-001).
 *
 * Surfaces the user's alert rules over /holdings/alerts. Reads land in
 * the standard list cache; writes invalidate the list so the page
 * stays in sync after create / update / delete / evaluate-now.
 *
 * staleTime: 30s mirrors the rest of /holdings/* — alert rule state
 * changes infrequently in the user's view (the scheduler is the main
 * mutator and runs at most once per hour).
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createAlertRule,
  deleteAlertRule,
  evaluateAlertRule,
  listAlertRules,
  updateAlertRule,
  type AlertEvaluationResult,
  type AlertRule,
  type AlertRuleCreateRequest,
  type AlertRuleUpdateRequest,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useAlertRules() {
  return useQuery<AlertRule[]>({
    queryKey: queryKeys.holdings.alerts.list(),
    queryFn: listAlertRules,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useCreateAlertRule() {
  const qc = useQueryClient();
  return useMutation<AlertRule, Error, AlertRuleCreateRequest>({
    mutationFn: createAlertRule,
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.holdings.alerts.all,
      });
    },
  });
}

export function useUpdateAlertRule() {
  const qc = useQueryClient();
  return useMutation<
    AlertRule,
    Error,
    { id: number; body: AlertRuleUpdateRequest }
  >({
    mutationFn: ({ id, body }) => updateAlertRule(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.holdings.alerts.all,
      });
    },
  });
}

export function useDeleteAlertRule() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: deleteAlertRule,
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.holdings.alerts.all,
      });
    },
  });
}

export function useEvaluateAlertRule() {
  const qc = useQueryClient();
  return useMutation<AlertEvaluationResult, Error, number>({
    mutationFn: evaluateAlertRule,
    onSuccess: () => {
      // Evaluate can transition status (ACTIVE → TRIGGERED) and update
      // last_evaluated_at — invalidate so the table refreshes.
      void qc.invalidateQueries({
        queryKey: queryKeys.holdings.alerts.all,
      });
    },
  });
}
