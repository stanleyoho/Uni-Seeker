"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalAccount, useJournalAccounts } from "@/hooks/use-journal";
import { AddTradeModal } from "@/components/journal/add-trade-modal";

function pnlColor(val: number) {
  if (val > 0) return "var(--stock-up)";
  if (val < 0) return "var(--stock-down)";
  return "var(--foreground)";
}

function fmt(n: number, dec = 0) {
  return n.toLocaleString("zh-TW", { maximumFractionDigits: dec });
}

export default function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const { data, isLoading } = useJournalAccount(accountId);
  const { data: accounts = [] } = useJournalAccounts();
  const [showModal, setShowModal] = useState(false);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--text-muted)" }}>載入中...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--stock-down)" }}>帳戶不存在</span>
      </div>
    );
  }

  const { account, positions } = data;
  const totalCost = positions.reduce((s, p) => s + Number(p.total_cost ?? 0), 0);
  const totalRealized = positions.reduce((s, p) => s + Number(p.realized_pnl), 0);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
            {account.name}
          </h2>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            {account.broker && `${account.broker} · `}{account.market} · {account.currency}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link href={`/journal/accounts/${accountId}/trades`}>
            <ClippedButton variant="cyan-ghost" size="sm">交易記錄</ClippedButton>
          </Link>
          <ClippedButton variant="green-solid" size="sm" onClick={() => setShowModal(true)}>
            + 新增交易
          </ClippedButton>
        </div>
      </div>

      {/* Account KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[
          { label: "持倉成本", value: fmt(totalCost) },
          { label: "已實現損益", value: fmt(totalRealized), color: pnlColor(totalRealized) },
          { label: "持倉數量", value: `${positions.length} 檔` },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            style={{
              padding: "12px 16px",
              background: "var(--glass-bg)",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", marginBottom: 4 }}>
              {label}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: color ?? "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Holdings Table */}
      <GlassPanel title="持倉明細" noPadding>
        {positions.length === 0 ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>
            尚無持倉。點擊右上角「＋ 新增交易」開始記錄。
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {["標的", "數量", "FIFO均價", "持倉成本", "已實現損益"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "8px 14px",
                        textAlign: h === "標的" ? "left" : "right",
                        color: "var(--text-muted)",
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        fontSize: 10,
                        textTransform: "uppercase",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, i) => {
                  const realized = Number(pos.realized_pnl);
                  const avgCost = Number(pos.avg_cost_fifo ?? 0);
                  const cost = Number(pos.total_cost ?? 0);
                  return (
                    <tr
                      key={pos.id}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                      }}
                    >
                      <td style={{ padding: "10px 14px", fontWeight: 700, color: "var(--foreground)" }}>
                        {pos.symbol}
                        <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>
                          {pos.market}
                        </span>
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace" }}>
                        {fmt(Number(pos.quantity), 4)}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                        {avgCost > 0 ? fmt(avgCost, 2) : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace" }}>
                        {cost > 0 ? fmt(cost) : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace", color: pnlColor(realized) }}>
                        {realized !== 0 ? (realized > 0 ? "+" : "") + fmt(realized) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>

      {showModal && (
        <AddTradeModal
          accounts={accounts}
          defaultAccountId={accountId}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
