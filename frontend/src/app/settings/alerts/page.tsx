"use client";

/**
 * Alert rules — /settings/alerts (UNI-ALERT-001).
 *
 * User-facing surface over the /holdings/alerts API. Lets the user
 * create, pause, resume, delete, and manually evaluate rules. Rules
 * triggered by the scheduler are surfaced with a TRIGGERED badge —
 * "evaluate now" or the next scheduled cycle re-tests after the user
 * resumes them.
 *
 * Layout: GlassPanel container, three sections —
 *   1. Header (title + refresh + create CTA)
 *   2. New-rule modal (collapsible inline form, not a portal)
 *   3. Rules table
 *
 * Decimal-as-string per project convention — threshold_value flows as
 * string the entire way through and we only Number() when rendering
 * locale-formatted percent.
 */

import { useMemo, useState } from "react";
import { useI18n } from "@/i18n/context";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import { useAuth } from "@/contexts/auth-context";
import {
  useAlertRules,
  useCreateAlertRule,
  useDeleteAlertRule,
  useEvaluateAlertRule,
  useUpdateAlertRule,
} from "@/hooks/use-alerts";
import type {
  AlertRuleCreateRequest,
  AlertRuleType,
  AlertStatus,
  AlertThresholdType,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POSITION_RULES: AlertRuleType[] = [
  "POSITION_PRICE_DROP",
  "POSITION_PRICE_RISE",
  "POSITION_PNL_PCT_ABOVE",
  "POSITION_PNL_PCT_BELOW",
];

const PORTFOLIO_RULES: AlertRuleType[] = [
  "PORTFOLIO_VALUE_ABOVE",
  "PORTFOLIO_VALUE_BELOW",
];

const RULE_TYPES: AlertRuleType[] = [...POSITION_RULES, ...PORTFOLIO_RULES];

const MARKETS = ["TW_TWSE", "TW_TPEX", "US_NYSE", "US_NASDAQ"] as const;

function isPositionRule(t: AlertRuleType): boolean {
  return POSITION_RULES.includes(t);
}

function isPnLRule(t: AlertRuleType): boolean {
  return (
    t === "POSITION_PNL_PCT_ABOVE" || t === "POSITION_PNL_PCT_BELOW"
  );
}

function isPortfolioRule(t: AlertRuleType): boolean {
  return PORTFOLIO_RULES.includes(t);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string | null, locale: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function statusColors(status: AlertStatus): { fg: string; border: string } {
  switch (status) {
    case "ACTIVE":
      return {
        fg: "var(--stock-up)",
        border: "var(--stock-up)",
      };
    case "TRIGGERED":
      return {
        fg: "var(--stock-down)",
        border: "var(--stock-down)",
      };
    case "PAUSED":
    default:
      return {
        fg: "var(--text-muted)",
        border: "var(--border-color)",
      };
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const { tr, locale } = useI18n();
  const { user } = useAuth();
  const query = useAlertRules();
  const createMut = useCreateAlertRule();
  const updateMut = useUpdateAlertRule();
  const deleteMut = useDeleteAlertRule();
  const evalMut = useEvaluateAlertRule();

  const [showForm, setShowForm] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Wrap in useMemo so the `?? []` fallback returns a referentially
  // stable empty array; otherwise the sortedRules useMemo below sees a
  // new dep identity on every render (react-hooks/exhaustive-deps).
  const rules = useMemo(() => query.data ?? [], [query.data]);
  const sortedRules = useMemo(
    () =>
      [...rules].sort((a, b) => {
        // Triggered first (need attention), then active, then paused.
        const order: Record<AlertStatus, number> = {
          TRIGGERED: 0,
          ACTIVE: 1,
          PAUSED: 2,
        };
        return order[a.status] - order[b.status];
      }),
    [rules],
  );

  if (!user) {
    return (
      <main className="relative flex-1 overflow-y-auto">
        <AmbientBackground />
        <div className="relative max-w-[1200px] mx-auto px-6 py-6">
          <GlassPanel>
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              {tr("auth.login")} required.
            </p>
          </GlassPanel>
        </div>
      </main>
    );
  }

  const ruleLabel = (t: AlertRuleType) =>
    tr(`settings.alerts.rule_${t.toLowerCase()}`);

  const statusLabel = (s: AlertStatus) =>
    tr(`settings.alerts.status_${s.toLowerCase()}`);

  return (
    <main className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      <div className="relative max-w-[1200px] mx-auto px-6 py-6 space-y-6">
        {/* Title */}
        <div>
          <h1
            className="text-[20px] font-bold uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            {tr("settings.alerts.title")}
          </h1>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
            }}
          >
            {tr("settings.alerts.subtitle")}
          </p>
        </div>

        {/* Action bar */}
        <GlassPanel>
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
                fontSize: 12,
                color: "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {rules.length} {tr("settings.alerts.column_name")}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <ClippedButton
                variant="cyan-ghost"
                size="sm"
                onClick={() => query.refetch()}
                disabled={query.isFetching}
              >
                {query.isFetching
                  ? tr("settings.alerts.refreshing")
                  : tr("settings.alerts.refresh")}
              </ClippedButton>
              <ClippedButton
                variant="red-solid"
                size="sm"
                onClick={() => {
                  setShowForm((v) => !v);
                  setCreateError(null);
                }}
              >
                {tr("settings.alerts.create")}
              </ClippedButton>
            </div>
          </div>
        </GlassPanel>

        {/* Create form */}
        {showForm && (
          <GlassPanel>
            <CreateRuleForm
              onCancel={() => {
                setShowForm(false);
                setCreateError(null);
              }}
              error={createError}
              saving={createMut.isPending}
              onSubmit={async (body) => {
                setCreateError(null);
                try {
                  await createMut.mutateAsync(body);
                  setShowForm(false);
                } catch (err) {
                  const e = err as Error & { status?: number };
                  if (e.message?.includes("limit_exceeded")) {
                    setCreateError(tr("settings.alerts.limit_exceeded"));
                  } else {
                    setCreateError(tr("settings.alerts.create_error"));
                  }
                }
              }}
            />
          </GlassPanel>
        )}

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
              {tr("settings.alerts.loading")}
            </div>
          ) : query.isError ? (
            <div
              style={{
                padding: "24px 0",
                fontSize: 13,
                color: "var(--accent-primary)",
              }}
            >
              {tr("settings.alerts.error")}
            </div>
          ) : sortedRules.length === 0 ? (
            <div
              style={{
                padding: "24px 0",
                fontSize: 13,
                color: "var(--text-muted)",
              }}
            >
              {tr("settings.alerts.no_rules")}
            </div>
          ) : (
            <div
              role="table"
              aria-label={tr("settings.alerts.title")}
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
                    "1fr 1.2fr 0.9fr 0.7fr 0.7fr 1.1fr 1.2fr",
                  gap: 10,
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
                  {tr("settings.alerts.column_name")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_rule_type")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_target")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_threshold")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_status")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_last_check")}
                </span>
                <span role="columnheader">
                  {tr("settings.alerts.column_actions")}
                </span>
              </div>

              {sortedRules.map((rule) => {
                const palette = statusColors(rule.status);
                const thresholdSuffix =
                  rule.threshold_type === "PCT" ? "%" : "";
                return (
                  <div
                    key={rule.id}
                    role="row"
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "1fr 1.2fr 0.9fr 0.7fr 0.7fr 1.1fr 1.2fr",
                      gap: 10,
                      padding: "10px 14px",
                      borderBottom: "1px solid var(--border-subtle)",
                      alignItems: "center",
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        color: "var(--foreground)",
                      }}
                    >
                      {rule.name}
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        color: "var(--text-secondary)",
                      }}
                    >
                      {ruleLabel(rule.rule_type)}
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        fontFamily: "var(--font-mono, ui-monospace)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {rule.symbol
                        ? `${rule.symbol}/${rule.market ?? ""}`
                        : tr("settings.alerts.rule_portfolio_value_above")}
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        fontVariantNumeric: "tabular-nums",
                        color: "var(--foreground)",
                      }}
                    >
                      {rule.threshold_value}
                      {thresholdSuffix}
                    </span>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        fontSize: 11,
                        color: palette.fg,
                        border: `1px solid ${palette.border}`,
                        letterSpacing: "0.02em",
                        width: "fit-content",
                      }}
                    >
                      {statusLabel(rule.status)}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--text-muted)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {formatTimestamp(rule.last_evaluated_at, locale)}
                    </span>
                    <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {rule.status === "ACTIVE" ? (
                        <ClippedButton
                          variant="cyan-ghost"
                          size="sm"
                          onClick={() =>
                            updateMut.mutate({
                              id: rule.id,
                              body: { status: "PAUSED" },
                            })
                          }
                          disabled={updateMut.isPending}
                        >
                          {tr("settings.alerts.action_pause")}
                        </ClippedButton>
                      ) : (
                        <ClippedButton
                          variant="cyan-ghost"
                          size="sm"
                          onClick={() =>
                            updateMut.mutate({
                              id: rule.id,
                              body: { status: "ACTIVE" },
                            })
                          }
                          disabled={updateMut.isPending}
                        >
                          {tr("settings.alerts.action_resume")}
                        </ClippedButton>
                      )}
                      <ClippedButton
                        variant="cyan-ghost"
                        size="sm"
                        onClick={() => evalMut.mutate(rule.id)}
                        disabled={evalMut.isPending}
                      >
                        {tr("settings.alerts.action_evaluate")}
                      </ClippedButton>
                      <ClippedButton
                        variant="red-ghost"
                        size="sm"
                        onClick={() => {
                          if (
                            window.confirm(
                              tr("settings.alerts.delete_confirm"),
                            )
                          ) {
                            deleteMut.mutate(rule.id);
                          }
                        }}
                        disabled={deleteMut.isPending}
                      >
                        {tr("settings.alerts.action_delete")}
                      </ClippedButton>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </GlassPanel>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Create-rule form
// ---------------------------------------------------------------------------

interface CreateRuleFormProps {
  onSubmit: (body: AlertRuleCreateRequest) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}

function CreateRuleForm(props: CreateRuleFormProps) {
  const { tr } = useI18n();
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState<AlertRuleType>(
    "POSITION_PRICE_DROP",
  );
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<string>("US_NASDAQ");
  const [thresholdValue, setThresholdValue] = useState("10");
  const [thresholdType, setThresholdType] = useState<AlertThresholdType>(
    "PCT",
  );

  const positionScoped = isPositionRule(ruleType);
  const pnlScoped = isPnLRule(ruleType);
  const portfolioScoped = isPortfolioRule(ruleType);

  // Auto-correct threshold type when the rule type's allowed set shrinks.
  const effectiveThresholdType: AlertThresholdType = portfolioScoped
    ? "ABSOLUTE"
    : pnlScoped
      ? "PCT"
      : thresholdType;

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const body: AlertRuleCreateRequest = {
          name: name.trim(),
          rule_type: ruleType,
          threshold_value: thresholdValue,
          threshold_type: effectiveThresholdType,
          symbol: positionScoped ? symbol.trim().toUpperCase() : null,
          market: positionScoped ? market : null,
        };
        await props.onSubmit(body);
      }}
      style={{ display: "flex", flexDirection: "column", gap: 12 }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
        }}
      >
        <Field label={tr("settings.alerts.form_name")}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            placeholder={tr("settings.alerts.form_name_placeholder")}
            style={inputStyle}
          />
        </Field>
        <Field label={tr("settings.alerts.form_rule_type")}>
          <select
            value={ruleType}
            onChange={(e) =>
              setRuleType(e.target.value as AlertRuleType)
            }
            style={inputStyle}
          >
            {RULE_TYPES.map((t) => (
              <option key={t} value={t}>
                {tr(`settings.alerts.rule_${t.toLowerCase()}`)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {positionScoped && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <Field label={tr("settings.alerts.form_symbol")}>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              required={positionScoped}
              maxLength={20}
              placeholder={tr("settings.alerts.form_symbol_placeholder")}
              style={inputStyle}
            />
          </Field>
          <Field label={tr("settings.alerts.form_market")}>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              style={inputStyle}
            >
              {MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
        }}
      >
        <Field label={tr("settings.alerts.form_threshold_value")}>
          <input
            value={thresholdValue}
            onChange={(e) => setThresholdValue(e.target.value)}
            required
            inputMode="decimal"
            style={inputStyle}
          />
        </Field>
        <Field label={tr("settings.alerts.form_threshold_type")}>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            {(
              [
                ["PCT", "settings.alerts.form_threshold_pct"],
                ["ABSOLUTE", "settings.alerts.form_threshold_abs"],
              ] as const
            ).map(([val, key]) => {
              const disabled =
                (val === "PCT" && portfolioScoped) ||
                (val === "ABSOLUTE" && pnlScoped);
              const active = effectiveThresholdType === val;
              return (
                <label
                  key={val}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: disabled ? "not-allowed" : "pointer",
                    color: disabled
                      ? "var(--text-muted)"
                      : active
                        ? "var(--accent-cyan)"
                        : "var(--text-secondary)",
                    fontSize: 12,
                  }}
                >
                  <input
                    type="radio"
                    name="threshold_type"
                    value={val}
                    checked={active}
                    disabled={disabled}
                    onChange={() => setThresholdType(val)}
                  />
                  {tr(key)}
                </label>
              );
            })}
          </div>
        </Field>
      </div>

      {props.error && (
        <div
          style={{
            fontSize: 12,
            color: "var(--accent-primary)",
            padding: "8px 10px",
            border: "1px solid var(--accent-primary)",
            background: "color-mix(in srgb, var(--accent-primary) 8%, transparent)",
          }}
        >
          {props.error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <ClippedButton
          variant="cyan-ghost"
          size="sm"
          onClick={props.onCancel}
          type="button"
          disabled={props.saving}
        >
          {tr("settings.alerts.form_cancel")}
        </ClippedButton>
        <ClippedButton
          variant="red-solid"
          size="sm"
          type="submit"
          disabled={props.saving}
        >
          {props.saving
            ? tr("settings.alerts.form_saving")
            : tr("settings.alerts.form_save")}
        </ClippedButton>
      </div>
    </form>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 10px",
  background: "var(--bg-secondary)",
  border: "1px solid var(--border-color)",
  color: "var(--foreground)",
  fontSize: 13,
  fontFamily: "var(--font-mono, ui-monospace)",
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <span
        style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--text-muted)",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}
