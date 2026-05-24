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
  getFxRate,
  getHoldingAccount,
  getHoldingDividend,
  getHoldingPosition,
  getHoldingTrade,
  getUserHoldingSummary,
  importHoldingsCsv,
  listHoldingAccounts,
  listHoldingDividends,
  listHoldingPositions,
  listHoldingTrades,
  executeRebalance,
  previewRebalance,
  updateHoldingAccount,
  updateHoldingDividend,
  updateHoldingTrade,
  type Currency,
  type HoldingAccount,
  type HoldingAccountCreateRequest,
  type HoldingAccountUpdateRequest,
  type HoldingDividend,
  type HoldingDividendCreateRequest,
  type HoldingDividendUpdateRequest,
  type HoldingMarket,
  type HoldingPositionListResponse,
  type HoldingSummary,
  type HoldingTrade,
  type HoldingTradeCreateRequest,
  type HoldingTradeUpdateRequest,
  type ImportResult,
  type MultiCurrencyHoldingSummary,
  type RebalanceExecuteResponse,
  type RebalanceRequest,
  type RebalanceResponse,
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

/**
 * User-wide holding summary.
 *
 * Pass `baseCurrency` to get the multi-currency response shape
 * (`MultiCurrencyHoldingSummary` with `by_currency` breakdown); omit
 * for the legacy single-currency response. The TS return is the union
 * — callers use `isMultiCurrencyHoldingSummary()` to discriminate.
 */
export function useUserHoldingSummary(baseCurrency?: Currency) {
  return useQuery<HoldingSummary | MultiCurrencyHoldingSummary>({
    queryKey: queryKeys.holdings.summary.user(baseCurrency),
    queryFn: () => getUserHoldingSummary(baseCurrency),
    staleTime: 30 * 1000,
  });
}

/**
 * Spot or historical FX rate. Sensible cache because FX rates change
 * slowly in our use case (we're not building a trading desk).
 *
 * Pass `asOf` (ISO YYYY-MM-DD) for historical; omit for spot. Same
 * currency on both sides short-circuits to `rate=1` without a network
 * round-trip.
 */
export function useFxRate(
  base: Currency | undefined,
  quote: Currency | undefined,
  asOf?: string,
) {
  return useQuery({
    queryKey: queryKeys.holdings.fx.rate(base ?? "", quote ?? "", asOf),
    queryFn: () => getFxRate(base as Currency, quote as Currency, asOf),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    enabled: Boolean(base) && Boolean(quote) && base !== quote,
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

// ---------------------------------------------------------------------------
// CSV Import (Phase 4)
// ---------------------------------------------------------------------------

interface ImportHoldingsCsvArgs {
  accountId: number;
  file: Blob | File | string;
  dryRun: boolean;
  /**
   * Optional explicit broker adapter key (Round 10). When omitted, the
   * backend auto-detects via BrokerParser.can_handle() heuristics.
   * Recognised keys: "interactive_brokers", "yuanta", "fubon", "schwab",
   * "fidelity", "generic".
   */
  brokerKey?: string | null;
}

/**
 * Bulk-import trades from a broker CSV.
 *
 * Invalidates trades + positions + summary on commit so the holdings
 * page reflects the new rows immediately. Dry-runs intentionally do NOT
 * invalidate — they don't mutate state, and refetching trades during a
 * preview would discard the user's open modal.
 */
export function useImportHoldingsCsv() {
  const qc = useQueryClient();
  return useMutation<ImportResult, Error, ImportHoldingsCsvArgs>({
    mutationFn: ({ accountId, file, dryRun, brokerKey }) =>
      importHoldingsCsv(accountId, file, dryRun, brokerKey ?? null),
    onSuccess: (data, vars) => {
      // Skip invalidation on dry-run (no state mutation) or atomic-rollback
      // commits (failed_rows > 0 means zero writes landed).
      if (vars.dryRun || data.failed_rows > 0) return;
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Rebalancing (Phase 5+, Pro-tier preview)
// ---------------------------------------------------------------------------

/**
 * Compute the trades required to reach a target allocation.
 *
 * Mutation rather than query because:
 *   - The targets are user-edited input — re-running on key changes
 *     would thrash the API while the user is typing.
 *   - The preview itself is non-destructive (no DB write) but emits an
 *     audit row on every call; firing it as a "side effect" of typing
 *     would pollute the audit log.
 *
 * We do NOT invalidate caches on success: preview is read-only.
 */
export function usePreviewRebalance() {
  return useMutation<RebalanceResponse, Error, RebalanceRequest>({
    mutationFn: (req) => previewRebalance(req),
  });
}

/**
 * Persist the suggested trades for a rebalance plan.
 *
 * Unlike preview, execute MUTATES state: every successful row writes a
 * `portfolio_trades` row through `PortfolioTradeService.record_trade`.
 * On success we invalidate trades + positions + summary so the holdings
 * page reflects the new state immediately.
 *
 * Partial-success semantics: the endpoint returns 200 even when some
 * trades land in `failed` (e.g. `InsufficientShares` from snapshot drift).
 * We still invalidate on every successful call — at least one row may
 * have committed, and revalidation is cheap.
 *
 * Whole-batch errors (403 feature_unavailable, 404 account_not_found,
 * 422 invalid_rebalance_input / account_id_required_for_execute) bubble
 * up as `ApiError` for the caller's error mapper to translate.
 */
export function useExecuteRebalance() {
  const qc = useQueryClient();
  return useMutation<RebalanceExecuteResponse, Error, RebalanceRequest>({
    mutationFn: (req) => executeRebalance(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.holdings.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.positions.all });
      qc.invalidateQueries({ queryKey: queryKeys.holdings.summary.all });
    },
  });
}
