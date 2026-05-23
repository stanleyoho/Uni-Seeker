"use client";

/**
 * Notification preferences — React Query hooks (Round 9 Y7).
 *
 * Two endpoints, two concerns:
 *   - `/me/notifications`              → transport identity (Telegram chat id).
 *   - `/institutional/filers/{id}/preferences` → per-filer notify toggle.
 *
 * Why a separate hook file from `use-notifications.ts`:
 *   The existing `use-notifications` hook owns the localStorage-backed
 *   alert-rule store (price alerts / screener summaries). That is a
 *   different concern from per-user transport preferences and per-filer
 *   13F toggles. Keeping the surfaces apart prevents the localStorage
 *   rule shape from leaking into the server-state query cache.
 *
 * Invalidation rules:
 *   - `useUpdateMeNotifications` → invalidate `me.notifications` only;
 *     transport identity is not consumed anywhere else in the cache.
 *   - `useUpdateFilerPreferences` → invalidate the filer list + that
 *     filer's detail. The list endpoint does not currently echo back
 *     `notify_on_new_filing`, but invalidating keeps the contract
 *     forward-compatible when/if Phase-3 widens the envelope.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getMeNotifications,
  updateFilerPreferences,
  updateMeNotifications,
  type F13SubscriptionPreferences,
  type MeNotificationSettings,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

// ---------------------------------------------------------------------------
// /me/notifications
// ---------------------------------------------------------------------------

/**
 * Fetch the current user's notification transport preferences.
 *
 * 30s staleTime mirrors other `/me/*` reads — long enough to skip a
 * round-trip when the user just toggled the page open after a save,
 * short enough that an external change (e.g. via the bot DM flow) shows
 * up within a single navigation.
 */
export function useMeNotifications() {
  return useQuery<MeNotificationSettings>({
    queryKey: queryKeys.me.notifications(),
    queryFn: getMeNotifications,
    staleTime: 30 * 1000,
  });
}

interface UpdateMeNotificationsArgs {
  telegram_chat_id: string | null;
}

/**
 * PATCH `/me/notifications`.
 *
 * `telegram_chat_id: null` is the canonical "stop alerts" gesture per
 * the backend contract (column becomes NULL). The hook accepts the
 * full body shape so future fields (email / line / webhook) drop in
 * additively without breaking call sites.
 */
export function useUpdateMeNotifications() {
  const qc = useQueryClient();
  return useMutation<
    MeNotificationSettings,
    Error,
    UpdateMeNotificationsArgs
  >({
    mutationFn: (args) => updateMeNotifications(args),
    onSuccess: (data) => {
      // Hand the fresh response into the cache so the page reflects
      // the persisted value without an extra round-trip.
      qc.setQueryData(queryKeys.me.notifications(), data);
      qc.invalidateQueries({ queryKey: queryKeys.me.notifications() });
    },
  });
}

// ---------------------------------------------------------------------------
// /institutional/filers/{id}/preferences
// ---------------------------------------------------------------------------

interface UpdateFilerPreferencesArgs {
  filerId: number;
  notify_on_new_filing: boolean;
}

/**
 * PATCH a single filer's `notify_on_new_filing`.
 *
 * Backend exposes only PATCH (no GET) — the initial display state on
 * the settings page is derived from the user's last action or the
 * backend default (`true`). On success we invalidate the filers list
 * and that filer's detail key so any panel re-reading them picks up
 * the new state once the backend widens the envelope.
 */
export function useUpdateFilerPreferences() {
  const qc = useQueryClient();
  return useMutation<
    F13SubscriptionPreferences,
    Error,
    UpdateFilerPreferencesArgs
  >({
    mutationFn: ({ filerId, notify_on_new_filing }) =>
      updateFilerPreferences(filerId, { notify_on_new_filing }),
    onSuccess: (_data, { filerId }) => {
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filers.list(),
      });
      qc.invalidateQueries({
        queryKey: queryKeys.institutional.filers.detail(filerId),
      });
    },
  });
}
