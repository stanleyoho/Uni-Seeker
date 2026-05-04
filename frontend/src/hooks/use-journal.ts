"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchJournalAccounts,
  fetchJournalAccount,
  createJournalAccount,
  fetchJournalTrades,
  createJournalTrade,
  fetchJournalGroups,
  fetchJournalGroup,
  createJournalGroup,
  fetchJournalAlerts,
  type JournalAccount,
  type JournalAccountCreate,
  type JournalTradeCreate,
  type JournalTradeListResponse,
  type JournalGroup,
  type JournalAlertsResponse,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useJournalAccounts() {
  return useQuery({
    queryKey: queryKeys.journal.accounts(),
    queryFn: fetchJournalAccounts,
    staleTime: 30 * 1000,
    placeholderData: (): JournalAccount[] => [],
  });
}

export function useJournalAccount(id: number) {
  return useQuery({
    queryKey: queryKeys.journal.account(id),
    queryFn: () => fetchJournalAccount(id),
    staleTime: 15 * 1000,
    enabled: id > 0,
  });
}

export function useCreateJournalAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JournalAccountCreate) => createJournalAccount(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.accounts() });
    },
  });
}

export function useJournalTrades(
  accountId: number,
  opts?: { symbol?: string; page?: number; page_size?: number },
) {
  return useQuery({
    queryKey: queryKeys.journal.trades(accountId, opts?.symbol, opts?.page),
    queryFn: () => fetchJournalTrades(accountId, opts),
    staleTime: 15 * 1000,
    enabled: accountId > 0,
    placeholderData: (): JournalTradeListResponse => ({ total: 0, items: [] }),
  });
}

export function useCreateJournalTrade(accountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JournalTradeCreate) => createJournalTrade(accountId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.account(accountId) });
      qc.invalidateQueries({ queryKey: queryKeys.journal.trades(accountId) });
      qc.invalidateQueries({ queryKey: queryKeys.journal.alerts() });
    },
  });
}

export function useJournalGroups() {
  return useQuery({
    queryKey: queryKeys.journal.groups(),
    queryFn: fetchJournalGroups,
    staleTime: 60 * 1000,
    placeholderData: (): JournalGroup[] => [],
  });
}

export function useJournalGroup(id: number) {
  return useQuery({
    queryKey: queryKeys.journal.group(id),
    queryFn: () => fetchJournalGroup(id),
    staleTime: 30 * 1000,
    enabled: id > 0,
  });
}

export function useCreateJournalGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof createJournalGroup>[0]) => createJournalGroup(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.groups() });
    },
  });
}

export function useJournalAlerts() {
  return useQuery({
    queryKey: queryKeys.journal.alerts(),
    queryFn: fetchJournalAlerts,
    staleTime: 60 * 1000,
    placeholderData: (): JournalAlertsResponse => ({ alerts: [] }),
  });
}
