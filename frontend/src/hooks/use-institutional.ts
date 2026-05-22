"use client";

/**
 * Institutional 13F — React Query hooks (Phase 2).
 *
 * One hook per /institutional/* endpoint. Invalidation rules follow the
 * shape of the underlying mutation:
 *
 *   - subscribe / unsubscribe   → filers.all (list refreshes; details by
 *                                  filer survive — we don't know which
 *                                  filer_id corresponds to a freshly
 *                                  resolved CIK without a round-trip).
 *   - refresh                   → invalidates the touched filer's detail
 *                                  + every filings/holdings/diff key for
 *                                  that filer. The list also refreshes
 *                                  because `latest_*` columns change.
 *
 * Decimal-as-string convention is preserved end-to-end; consumers convert
 * via `Number(...)` at render time (see components/institutional/types.ts).
 *
 * Note: `useFilerSearch` is enabled only when q.length >= 2 to match the
 * backend's 422 floor; this avoids burning a request per keystroke.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkSubscribeFilers,
  getDiff,
  getHoldings,
  getInstitutionalForStock,
  listFilings,
  listInstitutionalFilers,
  refreshFiler,
  searchFilers,
  subscribeFiler,
  unsubscribeFiler,
  type F13BulkSubscribeRequestItem,
  type F13BulkSubscribeResponse,
  type F13Diff,
  type F13Filer,
  type F13FilerSearchResult,
  type F13Filing,
  type F13HoldingsAtPeriod,
  type F13InstitutionalStock,
  type F13RefreshResult,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

// ---------------------------------------------------------------------------
// Filers
// ---------------------------------------------------------------------------

/**
 * List filers the current user is subscribed to.
 *
 * Backend returns alphabetical order; we keep that for stable rendering.
 * Empty-array placeholder keeps the filer table from flashing a spinner
 * during fast cached navigations.
 */
export function useInstitutionalFilers() {
  return useQuery({
    queryKey: queryKeys.institutional.filers.list(),
    queryFn: listInstitutionalFilers,
    staleTime: 30 * 1000,
    placeholderData: (): F13Filer[] => [],
  });
}

/**
 * Subscribe by CIK + display name.
 *
 * On success, refresh the filer list. Holdings / filings caches are
 * irrelevant because a brand-new filer has none yet (the user still needs
 * to trigger a refresh).
 */
export function useSubscribeFiler() {
  const qc = useQueryClient();
  return useMutation<F13Filer, Error, { cik: string; name: string }>({
    mutationFn: ({ cik, name }) => subscribeFiler(cik, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.institutional.filers.all });
    },
  });
}

/**
 * Bulk-subscribe to multiple filers in one atomic batch.
 *
 * Backend contract (`POST /institutional/filers/bulk`):
 *   - 201 envelope `{ subscribed, skipped_duplicates, errors }` on
 *     success / partial-success (per-row issues live in `errors[]`).
 *   - 403 `limit_exceeded:max_tracked_filers` when the projected count
 *     would exceed the user's tier quota → ATOMIC reject, no inserts.
 *
 * Invalidation: same as single-subscribe — refresh the filers list so
 * the newly added rows surface. We don't try to merge the inserted
 * filers into the existing cache because the list query already
 * returns the canonical alphabetised order.
 */
export function useBulkSubscribeFilers() {
  const qc = useQueryClient();
  return useMutation<
    F13BulkSubscribeResponse,
    Error,
    F13BulkSubscribeRequestItem[]
  >({
    mutationFn: (items) => bulkSubscribeFilers(items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.institutional.filers.all });
    },
  });
}

export function useUnsubscribeFiler() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (filerId) => unsubscribeFiler(filerId),
    onSuccess: () => {
      // Wipe the entire institutional cache — the unsubscribed filer's
      // holdings / filings / diff entries are now inaccessible (backend
      // returns 404), so any cached pages would render stale data.
      qc.invalidateQueries({ queryKey: queryKeys.institutional.all });
    },
  });
}

/**
 * Live filer search — typeahead style.
 *
 * Disabled for short queries; the backend rejects q.length < 2. We keep a
 * 5-second staleTime because EDGAR search results don't churn at typing
 * cadence and refetching every keystroke would burn rate-limit budget.
 */
export function useFilerSearch(q: string) {
  const trimmed = q.trim();
  return useQuery({
    queryKey: queryKeys.institutional.filers.search(trimmed),
    queryFn: () => searchFilers(trimmed),
    enabled: trimmed.length >= 2,
    staleTime: 5 * 1000,
    placeholderData: (): F13FilerSearchResult[] => [],
  });
}

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------

interface RefreshFilerArgs {
  filerId: number;
  maxQuarters?: number;
}

/**
 * Trigger an on-demand refresh.
 *
 * Invalidates everything tied to this filer: detail (latest_* columns
 * change), filings list, and any cached holdings / diff for any period.
 * The user's filer list is also refreshed so latest_filing_date /
 * latest_total_value_usd display promptly.
 */
export function useRefreshFiler() {
  const qc = useQueryClient();
  return useMutation<F13RefreshResult, Error, RefreshFilerArgs>({
    mutationFn: ({ filerId, maxQuarters }) =>
      refreshFiler(filerId, maxQuarters),
    onSuccess: (_data, { filerId }) => {
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filers.list(),
      });
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filers.detail(filerId),
      });
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filings.listByFiler(filerId),
      });
      // Holdings / diff keys are prefixed with the filer id; invalidate
      // the whole filings namespace to catch every cached period.
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filings.all,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Filings
// ---------------------------------------------------------------------------

export function useFilings(filerId: number | null) {
  return useQuery({
    queryKey: queryKeys.institutional.filings.listByFiler(filerId ?? 0),
    queryFn: () => listFilings(filerId as number),
    enabled: filerId != null && filerId > 0,
    staleTime: 30 * 1000,
    placeholderData: (): F13Filing[] => [],
  });
}

/**
 * Holdings at one period.
 *
 * `period` is either "latest" or an ISO date string that MUST match a
 * stored `report_period_end`. Empty / falsy period short-circuits — caller
 * passes "" before the period selector resolves a default.
 */
export function useHoldings(filerId: number | null, period: string) {
  return useQuery({
    queryKey: queryKeys.institutional.filings.holdings(
      filerId ?? 0,
      period || "latest",
    ),
    queryFn: () => getHoldings(filerId as number, period || "latest"),
    enabled: filerId != null && filerId > 0 && period.length > 0,
    staleTime: 60 * 1000,
  });
}

/**
 * Quarter-over-quarter diff.
 *
 * Both dates MUST exist as stored filings; the hook only fires when both
 * are non-empty strings. Caller is responsible for picking valid period
 * pairs from `useFilings(filerId)` output.
 */
export function useDiff(
  filerId: number | null,
  fromDate: string,
  toDate: string,
) {
  return useQuery<F13Diff>({
    queryKey: queryKeys.institutional.filings.diff(
      filerId ?? 0,
      fromDate,
      toDate,
    ),
    queryFn: () => getDiff(filerId as number, fromDate, toDate),
    enabled:
      filerId != null &&
      filerId > 0 &&
      fromDate.length > 0 &&
      toDate.length > 0 &&
      fromDate !== toDate,
    staleTime: 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Cross-stock institutional panel (Pro-only)
// ---------------------------------------------------------------------------

/**
 * Per-stock institutional ownership panel.
 *
 * Pro-only on the backend (`feature_unavailable:institutional_ownership_panel`
 * for lower tiers); the hook itself doesn't gate — the caller's <Suspense>
 * boundary handles the 403 by rendering an upgrade CTA.
 *
 * Exposed in Phase 2 for forward-compat with the per-stock detail page;
 * the Phase 2 /institutional page does not consume it directly.
 */
export function useInstitutionalForStock(symbol: string) {
  return useQuery<F13InstitutionalStock>({
    queryKey: queryKeys.institutional.stocks.bySymbol(symbol),
    queryFn: () => getInstitutionalForStock(symbol),
    enabled: symbol.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}
