"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createHoldingAccount,
  createHoldingDividend,
  createHoldingTrade,
  deleteHoldingAccount,
  deleteHoldingDividend,
  deleteHoldingTrade,
  getAccountHoldingSummary,
  getHoldingAccount,
  getHoldingDividend,
  getHoldingPosition,
  getHoldingTrade,
  getUserHoldingSummary,
  listHoldingAccounts,
  listHoldingDividends,
  listHoldingPositions,
  listHoldingTrades,
  updateHoldingAccount,
  updateHoldingDividend,
  updateHoldingTrade,
  type HoldingAccount,
  type HoldingAccountCreateRequest,
  type HoldingAccountUpdateRequest,
  type HoldingDividend,
  type HoldingDividendCreateRequest,
  type HoldingDividendUpdateRequest,
  type HoldingMarket,
  type HoldingPositionListResponse,
  type HoldingTrade,
  type HoldingTradeCreateRequest,
  type HoldingTradeUpdateRequest,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export function useHoldingAccounts() {
  return useQuery({
    queryKey: queryKeys.holdings.accounts.list(),
    queryFn: listHoldingAccounts,
    staleTime: 30 * 1000,
    placeholderData: (): HoldingAccount[] => [],
  });
}

export function useHoldingAccount(id: number) {
  return useQuery({
    queryKey: queryKeys.holdings.accounts.detail(id),
    queryFn: () => getHoldingAccount(id),
    staleTime: 15 * 1000,
    enabled: id > 0,
  });
}

export function useCreateHoldingAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HoldingAccountCreateRequest) => createHoldingAccount(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.accounts.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

export function useUpdateHoldingAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: HoldingAccountUpdateRequest }) =>
      updateHoldingAccount(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.accounts.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.accounts.list() });
    },
  });
}

export function useDeleteHoldingAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteHoldingAccount(id),
    onSuccess: () => {
      // Account delete cascades trades + positions + summary on backend.
      qc.invalidateQueries({ queryKey: queryKeys.holdings.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Trades
// ---------------------------------------------------------------------------

export function useHoldingTrades(
  accountId: number,
  limit?: number,
  offset?: number,
) {
  return useQuery({
    queryKey: queryKeys.holdings.trades.list(accountId, limit, offset),
    queryFn: () => listHoldingTrades(accountId, limit, offset),
    staleTime: 15 * 1000,
    enabled: accountId > 0,
    placeholderData: (): HoldingTrade[] => [],
  });
}

export function useHoldingTrade(id: number) {
  return useQuery({
    queryKey: queryKeys.holdings.trades.detail(id),
    queryFn: () => getHoldingTrade(id),
    staleTime: 15 * 1000,
    enabled: id > 0,
  });
}

export function useCreateHoldingTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HoldingTradeCreateRequest) => createHoldingTrade(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

export function useUpdateHoldingTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: HoldingTradeUpdateRequest }) =>
      updateHoldingTrade(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

export function useDeleteHoldingTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteHoldingTrade(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Positions (read-only, derived)
// ---------------------------------------------------------------------------

export function useHoldingPositions(accountId?: number) {
  return useQuery({
    queryKey: queryKeys.holdings.positions.list(accountId),
    queryFn: () => listHoldingPositions(accountId),
    staleTime: 15 * 1000,
    placeholderData: (): HoldingPositionListResponse => ({
      account_id: accountId ?? null,
      positions: [],
    }),
  });
}

export function useHoldingPosition(
  accountId: number,
  symbol: string,
  market: HoldingMarket,
) {
  return useQuery({
    queryKey: queryKeys.holdings.positions.detail(accountId, symbol, market),
    queryFn: () => getHoldingPosition(accountId, symbol, market),
    staleTime: 15 * 1000,
    enabled: accountId > 0 && symbol.length > 0,
  });
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

export function useUserHoldingSummary() {
  return useQuery({
    queryKey: queryKeys.holdings.summary.user(),
    queryFn: getUserHoldingSummary,
    staleTime: 30 * 1000,
  });
}

export function useAccountHoldingSummary(accountId: number) {
  return useQuery({
    queryKey: queryKeys.holdings.summary.account(accountId),
    queryFn: () => getAccountHoldingSummary(accountId),
    staleTime: 30 * 1000,
    enabled: accountId > 0,
  });
}

// ---------------------------------------------------------------------------
// Dividends
// ---------------------------------------------------------------------------

export function useHoldingDividends(
  accountId?: number,
  limit?: number,
  offset?: number,
) {
  return useQuery({
    queryKey: queryKeys.holdings.dividends.list(accountId, limit, offset),
    queryFn: () => listHoldingDividends(accountId, limit, offset),
    staleTime: 30 * 1000,
    placeholderData: (): HoldingDividend[] => [],
  });
}

export function useHoldingDividend(id: number) {
  return useQuery({
    queryKey: queryKeys.holdings.dividends.detail(id),
    queryFn: () => getHoldingDividend(id),
    staleTime: 30 * 1000,
    enabled: id > 0,
  });
}

export function useCreateHoldingDividend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HoldingDividendCreateRequest) => createHoldingDividend(body),
    onSuccess: () => {
      // CASH affects realized_pnl; STOCK rescales open lots (qty/avg_cost).
      // Either way, positions + summary must refresh.
      qc.invalidateQueries({ queryKey: queryKeys.holdings.dividends.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

export function useUpdateHoldingDividend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: HoldingDividendUpdateRequest }) =>
      updateHoldingDividend(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.dividends.detail(id) });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.dividends.all });
      // withholding_tax patches net_amount → realized_pnl projection;
      // safer to invalidate positions + summary too.
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

export function useDeleteHoldingDividend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteHoldingDividend(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.dividends.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}
