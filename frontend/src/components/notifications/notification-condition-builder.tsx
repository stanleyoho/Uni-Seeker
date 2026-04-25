"use client";

import { useI18n } from "@/i18n/context";

export interface NotificationCondition {
  type: "price" | "indicator" | "change";
  indicator?: string;
  operator: "above" | "below";
  value: number;
}

interface NotificationConditionBuilderProps {
  conditions: NotificationCondition[];
  onChange: (conditions: NotificationCondition[]) => void;
}

const INDICATOR_OPTIONS = ["RSI", "MACD", "KD", "SMA"] as const;

/**
 * Convert a structured conditions array into the flat JSON object the API expects.
 *
 * Examples:
 *   [{type:"price", operator:"above", value:100}]           -> {"price_above": 100}
 *   [{type:"indicator", indicator:"RSI", operator:"below", value:30}] -> {"RSI_below": 30}
 *   [{type:"change", operator:"above", value:5}]            -> {"daily_change_above": 5}
 */
export function conditionsToJson(
  conditions: NotificationCondition[],
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const c of conditions) {
    if (c.type === "price") {
      result[`price_${c.operator}`] = c.value;
    } else if (c.type === "indicator") {
      const ind = c.indicator ?? "RSI";
      result[`${ind}_${c.operator}`] = c.value;
    } else if (c.type === "change") {
      result[`daily_change_${c.operator}`] = c.value;
    }
  }
  return result;
}

export function NotificationConditionBuilder({
  conditions,
  onChange,
}: NotificationConditionBuilderProps) {
  const { t } = useI18n();

  const addCondition = () => {
    onChange([
      ...conditions,
      { type: "price", operator: "above", value: 0 },
    ]);
  };

  const removeCondition = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  const updateCondition = (
    index: number,
    field: keyof NotificationCondition,
    val: unknown,
  ) => {
    const updated = conditions.map((c, i) => {
      if (i !== index) return c;
      const next = { ...c, [field]: val };
      // Reset indicator when switching away from indicator type
      if (field === "type" && val !== "indicator") {
        delete next.indicator;
      }
      // Set default indicator when switching to indicator type
      if (field === "type" && val === "indicator" && !next.indicator) {
        next.indicator = "RSI";
      }
      return next;
    });
    onChange(updated);
  };

  const selectClass =
    "px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border-subtle)] text-white text-xs focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

  return (
    <div className="space-y-2">
      {conditions.map((cond, i) => (
        <div
          key={i}
          className="flex items-center gap-2 flex-wrap p-2.5 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)] animate-fade-in"
        >
          {/* Condition type */}
          <select
            value={cond.type}
            onChange={(e) =>
              updateCondition(
                i,
                "type",
                e.target.value as NotificationCondition["type"],
              )
            }
            className={selectClass}
          >
            <option value="price">{t.notifications.conditionPriceAlert}</option>
            <option value="indicator">
              {t.notifications.conditionIndicatorAlert}
            </option>
            <option value="change">
              {t.notifications.conditionDailyChange}
            </option>
          </select>

          {/* Indicator selector – only visible when type is "indicator" */}
          {cond.type === "indicator" && (
            <select
              value={cond.indicator ?? "RSI"}
              onChange={(e) => updateCondition(i, "indicator", e.target.value)}
              className={selectClass}
            >
              {INDICATOR_OPTIONS.map((ind) => (
                <option key={ind} value={ind}>
                  {ind}
                </option>
              ))}
            </select>
          )}

          {/* Operator */}
          <select
            value={cond.operator}
            onChange={(e) =>
              updateCondition(
                i,
                "operator",
                e.target.value as NotificationCondition["operator"],
              )
            }
            className={selectClass}
          >
            <option value="above">{t.notifications.above}</option>
            <option value="below">{t.notifications.below}</option>
          </select>

          {/* Value */}
          <input
            type="number"
            value={String(cond.value)}
            onChange={(e) => updateCondition(i, "value", Number(e.target.value))}
            className={`w-24 mono-nums ${selectClass}`}
            placeholder={t.screener.value}
          />

          {/* Delete */}
          <button
            type="button"
            onClick={() => removeCondition(i)}
            className="text-[var(--text-muted)] hover:text-red-400 transition-all duration-200 p-1.5 rounded-lg hover:bg-red-500/10"
            aria-label={t.notifications.delete}
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      ))}

      {/* Add condition button */}
      <button
        type="button"
        onClick={addCondition}
        className="flex items-center gap-1.5 px-3 py-2 bg-[var(--bg-secondary)] border border-dashed border-[var(--border-subtle)] text-[var(--text-secondary)] rounded-lg hover:border-[var(--accent-blue)]/50 hover:text-white hover:bg-[var(--card-hover)] transition-all duration-200 text-xs"
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v16m8-8H4"
          />
        </svg>
        {t.notifications.addCondition}
      </button>
    </div>
  );
}
