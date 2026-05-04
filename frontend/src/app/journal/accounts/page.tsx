"use client";

import { useState } from "react";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalAccounts, useCreateJournalAccount } from "@/hooks/use-journal";
import type { JournalAccountCreate } from "@/lib/api-client";

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none";
const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

function CreateAccountForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [broker, setBroker] = useState("");
  const [market, setMarket] = useState<"TW" | "US" | "CRYPTO">("TW");
  const [currency, setCurrency] = useState<"TWD" | "USD" | "USDT" | "BTC" | "ETH">("TWD");
  const [error, setError] = useState<string | null>(null);
  const createAccount = useCreateJournalAccount();

  async function handleCreate() {
    if (!name.trim()) { setError("請輸入帳戶名稱"); return; }
    try {
      await createAccount.mutateAsync({
        name: name.trim(),
        broker: broker || null,
        market,
        currency,
      } as JournalAccountCreate);
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "建立失敗");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 420 }}>
      <div>
        <label className={labelCls}>帳戶名稱</label>
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="元大證券" />
      </div>
      <div>
        <label className={labelCls}>券商（選填）</label>
        <input className={inputCls} value={broker} onChange={(e) => setBroker(e.target.value)} placeholder="元大" />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <label className={labelCls}>市場</label>
          <select className={inputCls} value={market} onChange={(e) => setMarket(e.target.value as "TW" | "US" | "CRYPTO")}>
            <option value="TW">TW 台股</option>
            <option value="US">US 美股</option>
            <option value="CRYPTO">加密貨幣</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>計價幣別</label>
          <select className={inputCls} value={currency} onChange={(e) => setCurrency(e.target.value as "TWD" | "USD" | "USDT" | "BTC" | "ETH")}>
            <option value="TWD">TWD</option>
            <option value="USD">USD</option>
            <option value="USDT">USDT</option>
          </select>
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--stock-down)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <ClippedButton variant="green-solid" size="sm" onClick={handleCreate} disabled={createAccount.isPending}>
          {createAccount.isPending ? "建立中..." : "建立帳戶"}
        </ClippedButton>
        <ClippedButton variant="cyan-ghost" size="sm" onClick={onDone}>取消</ClippedButton>
      </div>
    </div>
  );
}

export default function AccountsPage() {
  const { data: accounts = [], isLoading } = useJournalAccounts();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-6">
      <AmbientBackground />
      <GlassPanel
        title="帳戶列表"
        icon={<span style={{ color: "var(--accent-cyan)" }}>🏦</span>}
      >
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
          {!showForm && (
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setShowForm(true)}>
              + 新增帳戶
            </ClippedButton>
          )}
        </div>

        {showForm && <CreateAccountForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : accounts.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>尚未建立任何帳戶</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: showForm ? 20 : 0 }}>
            {accounts.map((acc) => (
              <Link key={acc.id} href={`/journal/accounts/${acc.id}`}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto auto",
                    alignItems: "center",
                    gap: 16,
                    padding: "12px 16px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "var(--foreground)" }}>
                      {acc.name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {acc.broker ? `${acc.broker} · ` : ""}{acc.market} · {acc.currency}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {new Date(acc.created_at).toLocaleDateString("zh-TW")}
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
