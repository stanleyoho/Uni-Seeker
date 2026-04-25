"use client";

import { useEffect, useState } from "react";
import {
  fetchNotificationRules,
  createNotificationRule,
  deleteNotificationRule,
  type NotificationRule,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import {
  NotificationConditionBuilder,
  conditionsToJson,
  type NotificationCondition,
} from "@/components/notifications/notification-condition-builder";

export default function NotificationsPage() {
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

  const inputClass =
    "px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border-subtle)] text-white text-xs placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

  return (
    <div className="p-3 md:p-4 max-w-5xl mx-auto animate-fade-in">
      <h1 className="text-xl md:text-2xl font-bold mb-4 text-white tracking-tight">{t.notifications.title}</h1>

      {/* Add Rule Form */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 mb-4">
        <h2 className="text-xs font-semibold mb-3 text-[var(--text-secondary)] uppercase tracking-wider">{t.notifications.addRule}</h2>
        <form onSubmit={handleCreate} className="space-y-2.5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.notifications.ruleName}
              className={inputClass}
            />
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              className={inputClass}
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
              className={inputClass}
            />
          </div>
          <NotificationConditionBuilder
            conditions={conditions}
            onChange={setConditions}
          />
          {formError && (
            <div className="px-2.5 py-1.5 bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-lg">
              <p className="text-red-400 text-xs">{formError}</p>
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-[var(--accent-blue)] text-white rounded-lg hover:bg-[var(--accent-blue-hover)] transition-all duration-200 disabled:opacity-50 text-xs font-medium"
          >
            {submitting ? (
              <span className="flex items-center gap-1.5">
                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {t.notifications.creating}
              </span>
            ) : (
              t.notifications.create
            )}
          </button>
        </form>
      </div>

      {/* Rules List */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <h2 className="text-xs font-semibold mb-3 text-[var(--text-secondary)] uppercase tracking-wider">{t.notifications.existingRules}</h2>

        {loading && <LoadingSpinner size="sm" />}

        {error && <ErrorState message={error} onRetry={loadRules} />}

        {!loading && rules.length === 0 && (
          <EmptyState message={t.notifications.noRules} />
        )}

        {rules.length > 0 && (
          <div className="space-y-1">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg px-3 py-2.5 transition-colors duration-150 hover:bg-[var(--card-hover)]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-medium text-white text-sm">{rule.name}</span>
                    <Badge>{rule.rule_type}</Badge>
                    <span className="text-xs text-[var(--accent-blue)] mono-nums font-medium">{rule.symbol}</span>
                    {rule.is_active ? (
                      <Badge variant="score-excellent">
                        <span className="w-1 h-1 rounded-full bg-[var(--score-excellent)] mr-1" />
                        {t.notifications.active}
                      </Badge>
                    ) : (
                      <Badge>
                        <span className="w-1 h-1 rounded-full bg-[var(--text-muted)] mr-1" />
                        {t.notifications.inactive}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[10px] text-[var(--text-muted)] mt-1 truncate mono-nums">
                    {JSON.stringify(rule.conditions)}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(rule.id)}
                  className="text-[var(--text-muted)] hover:text-red-400 transition-all duration-200 ml-3 shrink-0 p-1.5 rounded-lg hover:bg-red-500/10"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
