"use client";

/**
 * Audit log viewer — React Query hooks (Round 13).
 *
 * Read-only surface over ``/api/v1/me/audit-logs``. Lives in its own
 * hook file rather than ``use-notification-prefs.ts`` because the audit
 * viewer is a transparency/forensics tool, not a notification setting —
 * mixing the two would tempt cross-cache invalidation neither needs.
 *
 * staleTime: 30s mirrors the other ``/me/*`` reads. Audit rows are
 * append-only — the only way the cache can go stale is when the user
 * triggers a new mutation elsewhere in the app and comes back to this
 * page. A manual "Refresh" button on the page calls ``refetch()`` so
 * users can pull fresh data on demand.
 */

import { useQuery } from "@tanstack/react-query";
import {
  listMyAuditLogs,
  type AuditLogListResponse,
  type ListMyAuditLogsOptions,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useMyAuditLogs(opts: ListMyAuditLogsOptions = {}) {
  return useQuery<AuditLogListResponse>({
    queryKey: queryKeys.me.auditLogs(
      opts.limit,
      opts.offset,
      opts.eventTypes,
    ),
    queryFn: () => listMyAuditLogs(opts),
    staleTime: 30 * 1000,
    // Audit data is forensic — never silently refetch in the
    // background. The page exposes an explicit Refresh button.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}
