"use client";

import { useEffect, useState } from "react";
import {
  fetchNotificationRules,
  createNotificationRule,
  deleteNotificationRule,
  type NotificationRule,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import {
  NotificationConditionBuilder,
  conditionsToJson,
  type NotificationCondition,
} from "@/components/notifications/notification-condition-builder";

export default function AlertsPage() {
  const { t } = useI18n();
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState("price_alert");
  const [symbol, setSymbol] = useState("");
  const [conditions, setConditions] = useState<NotificationCondition[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadRules = async () => {
    try {
      const data = await fetchNotificationRules();
      setRules(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load rules");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadRules(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!name.trim() || !symbol.trim()) {
      setFormError(t.notifications.nameSymbolRequired);
      return;
    }

    const conditionsObj = conditionsToJson(conditions);

    setSubmitting(true);
    try {
      await createNotificationRule({
        name: name.trim(),
        rule_type: ruleType,
        symbol: symbol.trim().toUpperCase(),
        conditions: conditionsObj,
      });
      setName("");
      setSymbol("");
      setConditions([]);
      await loadRules();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteNotificationRule(id);
      setRules(rules.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete rule");
    }
  };

  const inputStyle: React.CSSProperties = {
    padding: "8px 12px",
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    color: "var(--foreground)",
    fontSize: 13,
    outline: "none",
    transition: "border-color 200ms",
    width: "100%",
  };

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4">
      <h1
        style={{
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: "-0.04em",
          color: "var(--foreground)",
          marginBottom: 20,
        }}
      >
        {t.notifications.title}
      </h1>

      {/* Add Rule Form */}
      <GlassPanel title={t.notifications.addRule} className="mb-6">
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.notifications.ruleName}
              style={inputStyle}
            />
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              style={inputStyle}
            >
              <option value="price_alert">{t.notifications.priceAlert}</option>
              <option value="indicator_alert">{t.notifications.indicatorAlert}</option>
              <option value="screener_alert">{t.notifications.screenerAlert}</option>
            </select>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder={t.notifications.symbolPlaceholder}
              style={inputStyle}
            />
          </div>

          <NotificationConditionBuilder
            conditions={conditions}
            onChange={setConditions}
          />

          {formError && (
            <div
              style={{
                padding: "8px 12px",
                background: "rgba(238,63,44,0.1)",
                border: "1px solid rgba(238,63,44,0.25)",
                borderRadius: 0,
              }}
            >
              <p style={{ color: "#EE3F2C", fontSize: 13, margin: 0 }}>{formError}</p>
            </div>
          )}

          <ClippedButton
            variant="red-solid"
            size="md"
            type="submit"
            disabled={submitting}
          >
            {submitting ? (
              <span className="flex items-center gap-2">
                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {t.notifications.creating}
              </span>
            ) : (
              t.notifications.create
            )}
          </ClippedButton>
        </form>
      </GlassPanel>

      {/* Rules List */}
      <GlassPanel title={t.notifications.existingRules}>
        {loading && <LoadingSpinner size="sm" />}

        {error && <ErrorState message={error} onRetry={loadRules} />}

        {!loading && rules.length === 0 && (
          <EmptyState message={t.notifications.noRules} />
        )}

        {rules.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border-color)",
                  }}
                >
                  {["Name", "Type", "Symbol", "Status", ""].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "8px 12px",
                        textAlign: "left",
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "#9CA3AF",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr
                    key={rule.id}
                    style={{
                      borderBottom: "1px solid var(--border-color)",
                      transition: "background 150ms",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background =
                        "rgba(255,255,255,0.03)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    {/* Name */}
                    <td
                      style={{
                        padding: "10px 12px",
                        fontSize: 14,
                        fontWeight: 500,
                        color: "var(--foreground)",
                      }}
                    >
                      {rule.name}
                    </td>

                    {/* Type */}
                    <td
                      style={{
                        padding: "10px 12px",
                        fontSize: 12,
                        color: "#9CA3AF",
                      }}
                    >
                      {rule.rule_type}
                    </td>

                    {/* Symbol */}
                    <td
                      style={{
                        padding: "10px 12px",
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "var(--accent-cyan, #00E5FF)",
                      }}
                    >
                      {rule.symbol}
                    </td>

                    {/* Status */}
                    <td style={{ padding: "10px 12px" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 12,
                          fontWeight: 500,
                          color: rule.is_active ? "#22C55E" : "#9CA3AF",
                        }}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: rule.is_active ? "#22C55E" : "#9CA3AF",
                            display: "inline-block",
                          }}
                        />
                        {rule.is_active
                          ? t.notifications.active
                          : t.notifications.inactive}
                      </span>
                    </td>

                    {/* Delete */}
                    <td style={{ padding: "10px 12px", textAlign: "right" }}>
                      <ClippedButton
                        variant="red-ghost"
                        size="sm"
                        onClick={() => handleDelete(rule.id)}
                      >
                        {t.notifications.delete}
                      </ClippedButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
