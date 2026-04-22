"use client";

import { useEffect, useState } from "react";
import {
  fetchNotificationRules,
  createNotificationRule,
  deleteNotificationRule,
  type NotificationRule,
} from "@/lib/api-client";

export default function NotificationsPage() {
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
      setFormError("Name and symbol are required.");
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
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Notification Rules</h1>

      {/* Add Rule Form */}
      <div className="bg-gray-800 rounded-lg p-4 mb-6">
        <h2 className="text-lg font-semibold mb-3">Add Rule</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Rule name"
              className="px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white text-sm placeholder-gray-500"
            />
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              className="px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white text-sm"
            >
              <option value="price_alert">Price Alert</option>
              <option value="indicator_alert">Indicator Alert</option>
              <option value="screener_alert">Screener Alert</option>
            </select>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="Symbol (e.g., 2330.TW, AAPL)"
              className="px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white text-sm placeholder-gray-500"
            />
          </div>
          <textarea
            value={conditionsJson}
            onChange={(e) => setConditionsJson(e.target.value)}
            placeholder='Conditions JSON, e.g. {"price_above": 100}'
            rows={3}
            className="w-full px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white text-sm placeholder-gray-500 font-mono"
          />
          {formError && <p className="text-red-500 text-sm">{formError}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 text-sm"
          >
            {submitting ? "Creating..." : "Create Rule"}
          </button>
        </form>
      </div>

      {/* Rules List */}
      <div className="bg-gray-800 rounded-lg p-4">
        <h2 className="text-lg font-semibold mb-3">Existing Rules</h2>
        {loading && <p className="text-gray-400 text-sm">Loading...</p>}
        {error && <p className="text-red-500 text-sm">{error}</p>}
        {!loading && rules.length === 0 && (
          <p className="text-gray-400 text-sm">No notification rules configured.</p>
        )}
        {rules.length > 0 && (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between bg-gray-700/50 rounded p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{rule.name}</span>
                    <span className="text-xs text-gray-400 bg-gray-600 rounded px-1.5 py-0.5">
                      {rule.rule_type}
                    </span>
                    <span className="text-sm text-blue-400">{rule.symbol}</span>
                    {rule.is_active ? (
                      <span className="text-xs text-green-400">Active</span>
                    ) : (
                      <span className="text-xs text-gray-500">Inactive</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1 truncate font-mono">
                    {JSON.stringify(rule.conditions)}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(rule.id)}
                  className="text-red-500 hover:text-red-400 text-sm ml-3 shrink-0"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
