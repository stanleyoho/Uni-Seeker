"use client";

/**
 * Audit Log Viewer — /settings/audit (Round 13).
 *
 * Surfaces the last 10 days of audit-log rows for the current user.
 * The page is a forensics tool, not a notification setting — the only
 * mutation it supports is the explicit "Refresh" button. Everything
 * else is read.
 *
 * Layout decisions:
 *   - Filter chips above the table mirror the chip pattern used on
 *     /institutional/filings.
 *   - Row expansion (click to reveal after_state + metadata JSON) keeps
 *     the table compact — most rows have null sidecars and would waste
 *     vertical space if inlined.
 *   - Pagination is offset/limit not cursor: ``total_count`` is cheap
 *     server-side and the client wants random-access "jump to page N"
 *     for forensics ("what did I do 8 days ago, around row 400?").
 *
 * STRATOS styling: GlassPanel container, ClippedButton for actions,
 * tabular-nums for timestamps, dark-luxe palette via CSS variables.
 */

import { useMemo, useState } from "react";
import { useI18n } from "@/i18n/context";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import { useAuth } from "@/contexts/auth-context";
import { useMyAuditLogs } from "@/hooks/use-audit";
import type { AuditLogEntry } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

/**
 * Filter chips — a curated subset of event_type values the user is
 * likely to want to slice by. The backend accepts any list, so future
 * additions are additive.
 */
const FILTER_CHIPS: { value: string; namespace: "portfolio" | "holdings" | "watchlist" | "auth" | "alert" | "billing" }[] = [
  { value: "user_login", namespace: "auth" },
  { value: "user_register", namespace: "auth" },
  { value: "device_added", namespace: "auth" },
  { value: "kyc_completed", namespace: "auth" },
  { value: "watchlist_added", namespace: "watchlist" },
  { value: "watchlist_removed", namespace: "watchlist" },
  { value: "trade_added", namespace: "holdings" },
  { value: "trade_updated", namespace: "holdings" },
  { value: "trade_deleted", namespace: "holdings" },
  { value: "portfolio_rebalanced", namespace: "portfolio" },
  { value: "alert_created", namespace: "alert" },
  { value: "alert_triggered", namespace: "alert" },
  { value: "tier_upgrade", namespace: "billing" },
  { value: "tier_downgrade", namespace: "billing" },
  { value: "subscription_cancel", namespace: "billing" },
  { value: "me_notifications_updated", namespace: "auth" },
];

/**
 * Map each event_type namespace prefix onto a STRATOS palette token.
 * A free-form ``event_type`` (one not in FILTER_CHIPS) falls back to
 * the muted text colour — there is no try/catch on the namespace
 * because mis-classifying a badge is a UI nit, not a correctness bug.
 */
const NAMESPACE_COLOR: Record<string, { fg: string; border: string }> = {
  portfolio: { fg: "var(--accent-cyan)", border: "var(--accent-cyan)" },
  holdings: { fg: "var(--stock-up)", border: "var(--stock-up)" },
  watchlist: { fg: "var(--accent-cyan)", border: "var(--accent-cyan)" },
  auth: { fg: "var(--text-secondary)", border: "var(--border-color)" },
  alert: { fg: "var(--stock-down)", border: "var(--stock-down)" },
  billing: { fg: "var(--accent-primary)", border: "var(--accent-primary)" },
};

function classifyEventType(eventType: string): keyof typeof NAMESPACE_COLOR | "other" {
  const known = FILTER_CHIPS.find((c) => c.value === eventType);
  if (known) return known.namespace;
  // Heuristic fallback: classify by leading verb.
  if (eventType.startsWith("portfolio")) return "portfolio";
  if (eventType.startsWith("holdings") || eventType.startsWith("trade"))
    return "holdings";
  if (eventType.startsWith("watchlist")) return "watchlist";
  if (eventType.startsWith("alert")) return "alert";
  if (
    eventType.startsWith("tier") ||
    eventType.startsWith("subscription") ||
    eventType.startsWith("billing")
  )
    return "billing";
  if (
    eventType.startsWith("user_") ||
    eventType.startsWith("device_") ||
    eventType === "kyc_completed"
  )
    return "auth";
  return "other";
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string, locale: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AuditLogPage() {
  const { tr, locale } = useI18n();
  const { user } = useAuth();

  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());

  const eventTypes = useMemo(
    () => (activeFilters.size > 0 ? Array.from(activeFilters) : undefined),
    [activeFilters],
  );

  const offset = page * PAGE_SIZE;
  const query = useMyAuditLogs({
    limit: PAGE_SIZE,
    offset,
    eventTypes,
  });

  const entries: AuditLogEntry[] = query.data?.entries ?? [];
  const totalCount = query.data?.total_count ?? 0;
  const hasMore = query.data?.has_more ?? false;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleFilter = (value: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
    setPage(0);
  };

  const clearFilters = () => {
    setActiveFilters(new Set());
    setPage(0);
  };

  // ----- Auth gate ---------------------------------------------------------
  if (!user) {
    return (
      <main className="relative flex-1 overflow-y-auto">
        <AmbientBackground />
        <div className="relative max-w-[1440px] mx-auto px-6 py-6">
          <GlassPanel>
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              {tr("auth.login")} required.
            </p>
          </GlassPanel>
        </div>
      </main>
    );
  }

  return (
    <main className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      <div className="relative max-w-[1200px] mx-auto px-6 py-6 space-y-6">
        {/* Page title */}
        <div>
          <h1
            className="text-[20px] font-bold uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            {tr("settings.audit.title")}
          </h1>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
            }}
          >
            {tr("settings.audit.subtitle")}
          </p>
        </div>

        {/* Filters + actions */}
        <GlassPanel>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "var(--text-muted)",
                }}
              >
                {tr("settings.audit.filter_label")}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {activeFilters.size > 0 && (
                  <ClippedButton
                    variant="red-ghost"
                    size="sm"
                    onClick={clearFilters}
                  >
                    {tr("settings.audit.clear_filters")}
                  </ClippedButton>
                )}
                <ClippedButton
                  variant="cyan-ghost"
                  size="sm"
                  onClick={() => query.refetch()}
                  disabled={query.isFetching}
                >
                  {query.isFetching
                    ? tr("settings.audit.refreshing")
                    : tr("settings.audit.refresh")}
                </ClippedButton>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                gap: 6,
                flexWrap: "wrap",
              }}
            >
              {FILTER_CHIPS.map((chip) => {
                const active = activeFilters.has(chip.value);
                const palette = NAMESPACE_COLOR[chip.namespace];
                return (
                  <button
                    key={chip.value}
                    type="button"
                    onClick={() => toggleFilter(chip.value)}
                    style={{
                      padding: "4px 10px",
                      fontSize: 11,
                      fontFamily: "var(--font-mono, ui-monospace)",
                      letterSpacing: "0.02em",
                      border: `1px solid ${active ? palette.fg : "var(--border-color)"}`,
                      background: active
                        ? "var(--card-hover)"
                        : "transparent",
                      color: active ? palette.fg : "var(--text-muted)",
                      cursor: "pointer",
                      transition: "background 0.18s ease, color 0.18s ease",
                    }}
                  >
                    {chip.value}
                  </button>
                );
              })}
            </div>
          </div>
        </GlassPanel>

        {/* Table */}
        <GlassPanel>
          {query.isLoading ? (
            <div
              style={{
                padding: "24px 0",
                fontSize: 13,
                color: "var(--text-muted)",
              }}
            >
              ...
            </div>
          ) : query.isError ? (
            <div
              style={{
                padding: "24px 0",
                fontSize: 13,
                color: "var(--accent-primary)",
              }}
            >
              {tr("settings.audit.error")}
            </div>
          ) : entries.length === 0 ? (
            <div
              style={{
                padding: "24px 0",
                fontSize: 13,
                color: "var(--text-muted)",
              }}
            >
              {tr("settings.audit.empty")}
            </div>
          ) : (
            <div
              role="table"
              aria-label={tr("settings.audit.title")}
              style={{
                display: "flex",
                flexDirection: "column",
                border: "1px solid var(--border-color)",
              }}
            >
              {/* Header row */}
              <div
                role="row"
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "180px 200px 120px 1fr",
                  gap: 12,
                  padding: "10px 14px",
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "var(--text-muted)",
                  background: "var(--bg-secondary)",
                  borderBottom: "1px solid var(--border-color)",
                }}
              >
                <span role="columnheader">
                  {tr("settings.audit.column_timestamp")}
                </span>
                <span role="columnheader">
                  {tr("settings.audit.column_event_type")}
                </span>
                <span role="columnheader">
                  {tr("settings.audit.column_resource")}
                </span>
                <span role="columnheader">
                  {tr("settings.audit.column_details")}
                </span>
              </div>

              {/* Body rows */}
              {entries.map((entry) => {
                const isExpanded = expanded.has(entry.id);
                const ns = classifyEventType(entry.event_type);
                const palette =
                  ns === "other"
                    ? {
                        fg: "var(--text-muted)",
                        border: "var(--border-color)",
                      }
                    : NAMESPACE_COLOR[ns];
                const hasSidecar =
                  entry.after_state !== null || entry.metadata !== null;

                return (
                  <div key={entry.id} role="row" style={{ display: "block" }}>
                    <button
                      type="button"
                      onClick={() => hasSidecar && toggleExpanded(entry.id)}
                      disabled={!hasSidecar}
                      style={{
                        display: "grid",
                        gridTemplateColumns:
                          "180px 200px 120px 1fr",
                        gap: 12,
                        width: "100%",
                        padding: "10px 14px",
                        alignItems: "center",
                        textAlign: "left",
                        background: isExpanded
                          ? "var(--card-hover)"
                          : "transparent",
                        border: "none",
                        borderBottom:
                          "1px solid var(--border-subtle)",
                        cursor: hasSidecar ? "pointer" : "default",
                        color: "var(--foreground)",
                        outline: "none",
                      }}
                    >
                      <span
                        style={{
                          fontSize: 12,
                          fontVariantNumeric: "tabular-nums",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {formatTimestamp(entry.created_at, locale)}
                      </span>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          fontSize: 11,
                          fontFamily:
                            "var(--font-mono, ui-monospace)",
                          color: palette.fg,
                          border: `1px solid ${palette.border}`,
                          letterSpacing: "0.02em",
                          width: "fit-content",
                        }}
                      >
                        {entry.event_type}
                      </span>
                      <span
                        style={{
                          fontSize: 12,
                          color: entry.resource_type
                            ? "var(--text-secondary)"
                            : "var(--text-muted)",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {entry.resource_type
                          ? `${entry.resource_type}${
                              entry.resource_id
                                ? ` #${entry.resource_id}`
                                : ""
                            }`
                          : "—"}
                      </span>
                      <span
                        style={{
                          fontSize: 12,
                          color: "var(--text-muted)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 8,
                        }}
                      >
                        <span>
                          {hasSidecar
                            ? tr(
                                isExpanded
                                  ? "settings.audit.collapse"
                                  : "settings.audit.expand",
                              )
                            : "—"}
                        </span>
                        {hasSidecar && (
                          <span
                            aria-hidden="true"
                            style={{
                              fontSize: 10,
                              color: "var(--text-muted)",
                            }}
                          >
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                      </span>
                    </button>

                    {isExpanded && hasSidecar && (
                      <div
                        style={{
                          padding: "12px 14px",
                          borderBottom:
                            "1px solid var(--border-subtle)",
                          background: "var(--bg-secondary)",
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: 16,
                        }}
                      >
                        <div>
                          <div
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-muted)",
                              marginBottom: 6,
                            }}
                          >
                            {tr("settings.audit.after_state")}
                          </div>
                          <pre
                            style={{
                              margin: 0,
                              fontSize: 11,
                              lineHeight: 1.5,
                              fontFamily:
                                "var(--font-mono, ui-monospace)",
                              color: "var(--text-secondary)",
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {entry.after_state
                              ? prettyJson(entry.after_state)
                              : tr("settings.audit.no_data")}
                          </pre>
                        </div>
                        <div>
                          <div
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-muted)",
                              marginBottom: 6,
                            }}
                          >
                            {tr("settings.audit.metadata")}
                          </div>
                          <pre
                            style={{
                              margin: 0,
                              fontSize: 11,
                              lineHeight: 1.5,
                              fontFamily:
                                "var(--font-mono, ui-monospace)",
                              color: "var(--text-secondary)",
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {entry.metadata
                              ? prettyJson(entry.metadata)
                              : tr("settings.audit.no_data")}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {totalCount > 0 && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                paddingTop: 16,
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              <div style={{ fontVariantNumeric: "tabular-nums" }}>
                {tr("settings.audit.pagination_summary")
                  .replace("{from}", String(offset + 1))
                  .replace(
                    "{to}",
                    String(offset + entries.length),
                  )
                  .replace("{total}", String(totalCount))}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <ClippedButton
                  variant="cyan-ghost"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || query.isFetching}
                >
                  {tr("settings.audit.prev")}
                </ClippedButton>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-secondary)",
                    alignSelf: "center",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {page + 1} / {totalPages}
                </span>
                <ClippedButton
                  variant="cyan-ghost"
                  size="sm"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!hasMore || query.isFetching}
                >
                  {tr("settings.audit.next")}
                </ClippedButton>
              </div>
            </div>
          )}
        </GlassPanel>

        {/* Footer note */}
        <div
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            textAlign: "center",
          }}
        >
          {tr("settings.audit.retention_note")}
        </div>
      </div>
    </main>
  );
}
