"use client";

import { useState } from "react";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalGroups, useCreateJournalGroup } from "@/hooks/use-journal";

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none";
const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

function CreateGroupForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const createGroup = useCreateJournalGroup();

  async function handleCreate() {
    if (!name.trim()) { setError("請輸入群組名稱"); return; }
    try {
      await createGroup.mutateAsync({ name: name.trim() });
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "建立失敗");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 400, marginBottom: 20 }}>
      <div>
        <label className={labelCls}>群組名稱</label>
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="我的投資組合" />
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--stock-down)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <ClippedButton variant="green-solid" size="sm" onClick={handleCreate} disabled={createGroup.isPending}>
          {createGroup.isPending ? "建立中..." : "建立群組"}
        </ClippedButton>
        <ClippedButton variant="cyan-ghost" size="sm" onClick={onDone}>取消</ClippedButton>
      </div>
    </div>
  );
}

export default function GroupsPage() {
  const { data: groups = [], isLoading } = useJournalGroups();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="relative flex-1 overflow-y-auto p-6">
      <AmbientBackground />
      <GlassPanel title="投資組合群組">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
          {!showForm && (
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setShowForm(true)}>
              + 新增群組
            </ClippedButton>
          )}
        </div>
        {showForm && <CreateGroupForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : groups.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            尚未建立任何群組。群組可將多個帳戶合併追蹤，並設定再平衡目標。
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: showForm ? 8 : 0 }}>
            {groups.map((g) => (
              <Link key={g.id} href={`/journal/groups/${g.id}`}>
                <div
                  style={{
                    padding: "12px 16px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    display: "grid",
                    gridTemplateColumns: "1fr auto",
                    alignItems: "center",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "var(--foreground)" }}>{g.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {g.members.length} 個帳戶 · {g.base_currency}
                    </div>
                  </div>
                  <span style={{ color: "var(--text-muted)" }}>→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
