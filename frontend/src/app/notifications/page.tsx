"use client";

import { useEffect, useState } from "react";
import {
  fetchNotificationRules,
  createNotificationRule,
  deleteNotificationRule,
  type NotificationRule,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

export default function NotificationsPage() {
  const { t } = useI18n();
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState("price_alert");
  const [symbol, setSymbol] = useState("");
  const [conditionsJson, setConditionsJson] = useState("{}");
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

  useEffect(() => {
    loadRules();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!name.trim() || !symbol.trim()) {
      setFormError(t.notifications.nameSymbolRequired);
      return;
    }

    let conditions: Record<string, unknown>;
    try {
      conditions = JSON.parse(conditionsJson);
    } catch {
      setFormError("Invalid JSON in conditions.");
      return;
    }

    setSubmitting(true);
    try {
      await createNotificationRule({
        name: name.trim(),
        rule_type: ruleType,
        symbol: symbol.trim().toUpperCase(),
        conditions,
      });
      setName("");
      setSymbol("");
      setConditionsJson("{}");
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

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-white tracking-tight">{t.notifications.title}</h1>

      {/* Add Rule Form */}
      <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5 mb-6">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.notifications.addRule}</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t.notifications.ruleName}
              className="px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white text-sm placeholder-[#64748b] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
            />
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              className="px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white text-sm focus:outline-none focus:border-blue-500 transition-all duration-200"
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
              className="px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white text-sm placeholder-[#64748b] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
            />
          </div>
          <textarea
            value={conditionsJson}
            onChange={(e) => setConditionsJson(e.target.value)}
            placeholder={t.notifications.conditionsPlaceholder}
            rows={3}
            className="w-full px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white text-sm placeholder-[#64748b] font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
          />
          {formError && (
            <div className="px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-red-400 text-sm">{formError}</p>
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all duration-200 disabled:opacity-50 text-sm font-medium shadow-lg shadow-blue-600/20"
          >
            {submitting ? (
              <span className="flex items-center gap-2">
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {t.notifications.creating}
              </span>
            ) : (
              t.notifications.create
            )}
          </button>
        </form>
      </div>

      {/* Rules List */}
      <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5">
        <h2 className="text-lg font-semibold mb-4 text-white">{t.notifications.existingRules}</h2>
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-[#1e293b] border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}
        {error && (
          <div className="px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg mb-3">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}
        {!loading && rules.length === 0 && (
          <div className="text-center py-12">
            <svg className="w-12 h-12 mx-auto text-[#1e293b] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            <p className="text-[#64748b] text-sm">{t.notifications.noRules}</p>
          </div>
        )}
        {rules.length > 0 && (
          <div className="space-y-2">
            {rules.map((rule, i) => (
              <div
                key={rule.id}
                className="flex items-center justify-between bg-[#111827] border border-[#1e293b] rounded-xl p-4 transition-all duration-200 hover:border-[#253449]"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-white">{rule.name}</span>
                    <span className="text-xs text-[#64748b] bg-[#1a2332] border border-[#1e293b] rounded-md px-2 py-0.5">
                      {rule.rule_type}
                    </span>
                    <span className="text-sm text-blue-400 font-mono font-medium">{rule.symbol}</span>
                    {rule.is_active ? (
                      <span className="flex items-center gap-1 text-xs text-green-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                        {t.notifications.active}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-[#64748b]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#64748b]" />
                        {t.notifications.inactive}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[#64748b] mt-1.5 truncate font-mono">
                    {JSON.stringify(rule.conditions)}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(rule.id)}
                  className="text-[#64748b] hover:text-red-400 transition-all duration-200 text-sm ml-4 shrink-0 p-2 rounded-lg hover:bg-red-500/10"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
