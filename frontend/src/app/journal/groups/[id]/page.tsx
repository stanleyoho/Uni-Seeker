"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel } from "@/components/stratos/primitives";
import { useJournalGroup, useJournalAlerts } from "@/hooks/use-journal";

export default function GroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const groupId = Number(id) || 0;
  const { data: group, isLoading } = useJournalGroup(groupId);
  const { data: alertsData } = useJournalAlerts();
  const groupAlerts = (alertsData?.alerts ?? []).filter(
    (a) => a.scope === "group" && a.scope_id === groupId,
  );

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--text-muted)" }}>載入中...</span>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--stock-down)" }}>群組不存在</span>
      </div>
    );
  }

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
          {group.name}
        </h2>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          基準幣別：{group.base_currency} · {group.members.length} 個帳戶
        </div>
      </div>

      {/* Member Accounts */}
      <GlassPanel title="成員帳戶">
        {group.members.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>尚無帳戶成員</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {group.members.map((m) => (
              <Link key={m.account_id} href={`/journal/accounts/${m.account_id}`}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto auto",
                    alignItems: "center",
                    gap: 16,
                    padding: "10px 14px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, color: "var(--foreground)" }}>
                      {m.account.name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {m.account.market} · {m.account.currency}
                    </div>
                  </div>
                  {m.target_weight && (
                    <div style={{ fontSize: 12, color: "var(--accent-cyan)", fontFamily: "monospace" }}>
                      目標 {(Number(m.target_weight) * 100).toFixed(0)}%
                    </div>
                  )}
                  <span style={{ color: "var(--text-muted)" }}>→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </GlassPanel>

      {/* Group-level Rebalance Alerts */}
      {groupAlerts.length > 0 && (
        <GlassPanel title="群組再平衡警示">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {groupAlerts.map((a) => {
              const dev = Number(a.deviation);
              const isOver = a.direction === "over";
              return (
                <div
                  key={`${a.scope_id}-${a.symbol}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: isOver ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)",
                    borderLeft: `3px solid ${isOver ? "var(--stock-down)" : "#f59e0b"}`,
                    fontSize: 12,
                  }}
                >
                  <span style={{ fontWeight: 700, color: "var(--foreground)" }}>{a.symbol}</span>
                  <span style={{ color: isOver ? "var(--stock-down)" : "#f59e0b", fontFamily: "monospace" }}>
                    {isOver ? "+" : ""}{(dev * 100).toFixed(1)}% 偏差
                  </span>
                </div>
              );
            })}
          </div>
        </GlassPanel>
      )}

      {/* Placeholder for future group performance chart */}
      <GlassPanel title="群組績效圖">
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          群組資產曲線將在日快照 cron job 啟用後顯示（Plan C）
        </div>
      </GlassPanel>
    </div>
  );
}
