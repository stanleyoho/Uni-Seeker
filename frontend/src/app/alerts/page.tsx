"use client";

import { useState } from "react";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
import { ConditionBuilder } from "@/components/screener/condition-builder";
import { useNotifications } from "@/hooks/use-notifications";
import { type ScreenCondition } from "@/lib/api-client";

export default function AlertsPage() {
  const { rules, addRule, removeRule, toggleRule } = useNotifications();
  const [showBuilder, setShowBuilder] = useState(false);
  const [ruleName, setRuleName] = useState("");
  const [conditions, setConditions] = useState<ScreenCondition[]>([]);

  const handleSaveRule = () => {
    if (ruleName.trim() && conditions.length > 0) {
      addRule({
        id: Date.now().toString(),
        name: ruleName,
        conditions: conditions,
        is_active: true,
      });
      setRuleName("");
      setConditions([]);
      setShowBuilder(false);
    }
  };

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in space-y-6">
        <div className="flex items-end justify-between mb-8 border-b border-[var(--border-subtle)] pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              Alerts & Notifications
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {rules.length} ACTIVE MONITORING RULES
            </p>
          </div>
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => setShowBuilder(!showBuilder)}
          >
            {showBuilder ? "CANCEL" : "CREATE NEW RULE"}
          </ClippedButton>
        </div>

        {showBuilder && (
          <GlassPanel title="ALERT RULE BUILDER">
            <div className="space-y-6">
              <input
                type="text"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                placeholder="Name your alert rule (e.g., 'RSI Oversold')"
                className="w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm font-bold text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none transition-all"
              />
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
                  TRIGGER CONDITIONS
                </h4>
                <ConditionBuilder conditions={conditions} onChange={setConditions} logicOperator="AND" onLogicChange={() => {}} />
              </div>
              <div className="flex justify-end gap-4 pt-4 border-t border-[var(--border-subtle)]">
                <ClippedButton variant="white-solid" size="md" onClick={() => setShowBuilder(false)}>
                  DISCARD
                </ClippedButton>
                <ClippedButton variant="cyan-ghost" size="md" onClick={handleSaveRule}>
                  SAVE & ACTIVATE
                </ClippedButton>
              </div>
            </div>
          </GlassPanel>
        )}

        <GlassPanel title="ACTIVE RULES" noPadding>
          <div className="divide-y divide-[var(--border-subtle)]">
            {rules.map(rule => (
              <div key={rule.id} className="flex items-center justify-between p-4 group">
                <div>
                  <p className={`font-bold text-sm ${rule.is_active ? 'text-[var(--foreground)]' : 'text-[var(--text-muted)]'}`}>
                    {rule.name}
                  </p>
                  <p className="text-xs text-[var(--text-muted)] mt-1 font-mono">
                    {rule.conditions.map(c => `${c.indicator} ${c.op} ${c.value}`).join(' AND ')}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <button onClick={() => toggleRule(rule.id)} className={`w-10 h-5 rounded-full p-0.5 transition-colors ${rule.is_active ? 'bg-[var(--accent-primary)]' : 'bg-[var(--bg-secondary)]'}`}>
                    <span className={`block w-4 h-4 rounded-full bg-white transform transition-transform ${rule.is_active ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                  <button onClick={() => removeRule(rule.id)} className="text-[var(--text-muted)] hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
          {rules.length === 0 && (
            <div className="py-20 text-center text-sm text-[var(--text-muted)] uppercase font-bold tracking-widest">
              NO ACTIVE ALERT RULES
            </div>
          )}
        </GlassPanel>
      </main>
    </div>
  );
}
