// ---------------------------------------------------------------------------
// Watchlist localStorage → API migration (Round 6 / WATCH-001)
//
// One-shot utility invoked from /portfolio when the user first lands on the
// page after the API-backed watchlist ships. We read whatever the legacy
// `useWatchlist` hook persisted under the `uni-seeker-watchlist` key,
// reconcile it against the server's current watchlist, and call the API
// to insert anything the server doesn't already know about. On success the
// legacy key is cleared so the migration never runs twice.
//
// Design choices worth calling out:
//
//   - We DELIBERATELY use the single-symbol `addToWatchlist` rather than
//     the new `/bulk` endpoint for the migration path. Reasons:
//       (a) Migration is best-effort + per-row reportable. The bulk
//           endpoint short-circuits the WHOLE batch with 403 when over
//           quota, but during migration we'd rather insert what fits
//           and report the rest as `failed`.
//       (b) Sequential add lets us stop early on the first 403 quota
//           response (Free tier hit cap) without having to model
//           "we sent 8 but only 4 fit" as a separate code path.
//     Migration volume is small (legacy localStorage was capped at the
//     same 10-item soft limit) so request count is fine.
//
//   - The 409 conflict path is mapped to `skipped`, not `failed`. A 409
//     means the symbol is ALREADY on the server's watchlist — that's a
//     successful migration outcome, not an error.
//
//   - We swallow JSON parse errors on the legacy key. If the stored
//     value is corrupt we treat it as an empty migration (and still
//     clear the key) — better than crashing the whole page mount.
//
//   - This module is a no-op on the server (Node SSR) — every entry
//     point guards on `typeof window === "undefined"`.
// ---------------------------------------------------------------------------

import { ApiError, addToWatchlist, listWatchlist } from "@/lib/api-client";

const LEGACY_KEY = "uni-seeker-watchlist";

export interface LegacyWatchlistItem {
  symbol: string;
  name?: string;
  market?: string;
  addedAt?: string;
}

export interface MigrationFailure {
  symbol: string;
  /** snake_case identifier: `tier_cap`, `unknown_symbol`, `network`, etc. */
  reason: string;
}

export interface MigrationResult {
  migrated: number;
  skipped: number;
  failed: MigrationFailure[];
}

/**
 * Cheap check used by callers to decide whether to render the migration
 * banner at all. Does NOT parse — only checks for presence.
 */
export function hasLegacyWatchlist(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(LEGACY_KEY) !== null;
  } catch {
    // Some browsers throw on localStorage access in private mode.
    return false;
  }
}

function readLegacy(): LegacyWatchlistItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Filter out malformed rows so the migration never crashes mid-loop.
    return parsed.filter(
      (x): x is LegacyWatchlistItem =>
        x &&
        typeof x === "object" &&
        typeof (x as { symbol?: unknown }).symbol === "string" &&
        (x as { symbol: string }).symbol.trim().length > 0,
    );
  } catch {
    return [];
  }
}

function clearLegacy(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(LEGACY_KEY);
  } catch {
    // Best effort — if removal fails we'll retry next mount.
  }
}

/**
 * Map an ApiError from `addToWatchlist` to a migration outcome.
 *
 * Return value:
 *   - "skip"   — already on the watchlist (409). NOT a failure.
 *   - "stop"   — Free tier cap (403). Caller should break the loop and
 *                mark the rest as `tier_cap`.
 *   - reason   — terminal failure for this single symbol.
 */
function classifyError(err: unknown): "skip" | "stop" | string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "skip";
    if (err.status === 403 && err.message.includes("watchlist_limit_exceeded")) {
      return "stop";
    }
    if (err.status === 404) return "unknown_symbol";
    if (err.status === 422) return "invalid_symbol";
    if (err.status === 401) return "unauthenticated";
    return `api_${err.status}`;
  }
  return "network";
}

/**
 * Run the one-shot migration.
 *
 * Flow:
 *   1. Read + sanitise localStorage.
 *   2. If empty: clear key + return zeros.
 *   3. Fetch current API watchlist. On fetch failure, abort BEFORE
 *      mutating anything — we don't want to re-insert items that already
 *      exist server-side just because we couldn't see them.
 *   4. For each legacy symbol NOT already on the server, call
 *      `addToWatchlist`. Track migrated / skipped / failed by class.
 *   5. On Free-tier 403, mark remaining symbols as `tier_cap` and break.
 *   6. Always clear the legacy key at the end so this runs once.
 */
export async function migrateLocalWatchlistToApi(): Promise<MigrationResult> {
  const legacy = readLegacy();
  if (legacy.length === 0) {
    clearLegacy();
    return { migrated: 0, skipped: 0, failed: [] };
  }

  let existingSymbols: Set<string>;
  try {
    const remote = await listWatchlist();
    existingSymbols = new Set(remote.map((r) => r.symbol));
  } catch (err) {
    // Couldn't see the server's view — bail and keep the legacy data so
    // the user can retry. The caller's banner should still render.
    const reason = err instanceof ApiError ? `api_${err.status}` : "network";
    return {
      migrated: 0,
      skipped: 0,
      failed: legacy.map((l) => ({ symbol: l.symbol, reason })),
    };
  }

  let migrated = 0;
  let skipped = 0;
  const failed: MigrationFailure[] = [];

  // Pre-skip anything already on the server. These count as "skipped" from
  // the user's POV — their localStorage entry made it to the cloud, even
  // if it was put there manually instead of by us.
  const toMigrate: LegacyWatchlistItem[] = [];
  for (const item of legacy) {
    if (existingSymbols.has(item.symbol)) {
      skipped += 1;
    } else {
      toMigrate.push(item);
    }
  }

  let hitTierCap = false;
  for (let i = 0; i < toMigrate.length; i += 1) {
    const item = toMigrate[i];
    if (hitTierCap) {
      failed.push({ symbol: item.symbol, reason: "tier_cap" });
      continue;
    }
    try {
      await addToWatchlist(item.symbol);
      migrated += 1;
    } catch (err) {
      const cls = classifyError(err);
      if (cls === "skip") {
        // Server reports already-exists — treat as success for migration.
        skipped += 1;
      } else if (cls === "stop") {
        // Free tier cap reached. Remaining items get tier_cap.
        hitTierCap = true;
        failed.push({ symbol: item.symbol, reason: "tier_cap" });
      } else {
        failed.push({ symbol: item.symbol, reason: cls });
      }
    }
  }

  // Only clear the key on a clean-ish run. Even if some items failed, we
  // still clear — the failures are reported in the banner and re-running
  // the migration won't help (the legacy data is still there in localStorage
  // until cleared, but it's no longer the source of truth post-Round 5.2).
  clearLegacy();

  return { migrated, skipped, failed };
}
